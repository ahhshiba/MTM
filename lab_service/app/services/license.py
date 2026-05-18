# app/services/license.py
"""
商用等級離線授權系統
- Ed25519 數位簽章驗證
- 多組件硬體指紋綁定 (fuzzy match)
- 防改系統時間 (Redis 單調時間戳 + NTP + DB)
"""
from __future__ import annotations

import base64
import datetime
import enum
import hashlib
import json
import logging
import os
import re
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Ed25519 公鑰 (由 tools/generate_license.py keygen 生成，嵌入此處)
#  首次 keygen 後請替換此 bytes
# ═══════════════════════════════════════════════════════════════
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAPtHjYGBig0eFjMXfHm3PkZ0275hp47X1RwmmanPORQM=
-----END PUBLIC KEY-----"""


# ═══════════════════════════════════════════════════════════════
# License 狀態
# ═══════════════════════════════════════════════════════════════
class LicenseStatus(str, enum.Enum):
    ACTIVE = "active"                # 全功能
    HISTORY_ONLY = "history_only"    # 只能調閱歷史
    EXPIRED = "expired"              # 完全鎖定
    INVALID = "invalid"              # license 無效 (簽章不合/不存在)
    TAMPERED = "tampered"            # 偵測到時間竄改


# ═══════════════════════════════════════════════════════════════
# 硬體指紋
# ═══════════════════════════════════════════════════════════════
class HardwareFingerprint:
    """收集多組件硬體特徵，生成複合指紋"""

    @staticmethod
    def _get_mac_addresses() -> List[str]:
        """取得所有實體網卡的 MAC address (排除虛擬網卡)"""
        macs = []
        try:
            # 使用 /sys/class/net 取得網卡資訊
            net_dir = Path("/sys/class/net")
            if net_dir.exists():
                for iface in sorted(net_dir.iterdir()):
                    name = iface.name
                    # 排除虛擬網卡
                    if name in ("lo",) or name.startswith(("veth", "docker", "br-", "virbr")):
                        continue
                    addr_file = iface / "address"
                    if addr_file.exists():
                        mac = addr_file.read_text().strip().upper()
                        if mac and mac != "00:00:00:00:00:00":
                            macs.append(mac)
        except Exception as e:
            logger.warning(f"Failed to get MAC addresses: {e}")

        # fallback: uuid.getnode()
        if not macs:
            import uuid
            node = uuid.getnode()
            mac = ":".join(f"{(node >> (8 * i)) & 0xFF:02X}" for i in reversed(range(6)))
            macs.append(mac)

        return sorted(set(macs))

    @staticmethod
    def _get_disk_serial() -> str:
        """取得主磁碟序號"""
        try:
            result = subprocess.run(
                ["lsblk", "-dno", "SERIAL"],
                capture_output=True, text=True, timeout=5,
            )
            serials = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
            return serials[0] if serials else ""
        except Exception as e:
            logger.warning(f"Failed to get disk serial: {e}")
            return ""

    @staticmethod
    def _get_cpu_info() -> str:
        """取得 CPU 型號 + 核心數"""
        try:
            model = ""
            cores = 0
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name") and not model:
                        model = line.split(":", 1)[1].strip()
                    if line.startswith("processor"):
                        cores += 1
            return f"{model}|{cores}cores"
        except Exception as e:
            logger.warning(f"Failed to get CPU info: {e}")
            return ""

    @staticmethod
    def _get_board_serial() -> str:
        """取得主機板序號"""
        # 嘗試多種方式
        for path in [
            "/sys/class/dmi/id/board_serial",
            "/sys/class/dmi/id/product_serial",
            "/sys/class/dmi/id/product_uuid",
        ]:
            try:
                content = Path(path).read_text().strip()
                if content and content.lower() not in ("", "none", "default string", "to be filled by o.e.m."):
                    return content
            except (PermissionError, FileNotFoundError):
                continue

        # fallback: dmidecode
        try:
            result = subprocess.run(
                ["dmidecode", "-s", "baseboard-serial-number"],
                capture_output=True, text=True, timeout=5,
            )
            serial = result.stdout.strip()
            if serial and serial.lower() not in ("none", "default string"):
                return serial
        except Exception:
            pass

        return ""

    @staticmethod
    def _get_hostname() -> str:
        return socket.gethostname()

    @classmethod
    def collect(cls) -> Dict[str, Any]:
        """收集所有硬體組件資訊"""
        components = {
            "mac_addresses": cls._get_mac_addresses(),
            "disk_serial": cls._get_disk_serial(),
            "cpu_info": cls._get_cpu_info(),
            "board_serial": cls._get_board_serial(),
            "hostname": cls._get_hostname(),
        }

        # 計算各組件的 hash
        component_hashes = {
            "mac": hashlib.sha256("|".join(components["mac_addresses"]).encode()).hexdigest(),
            "disk": hashlib.sha256(components["disk_serial"].encode()).hexdigest(),
            "cpu": hashlib.sha256(components["cpu_info"].encode()).hexdigest(),
            "board": hashlib.sha256(components["board_serial"].encode()).hexdigest(),
            "hostname": hashlib.sha256(components["hostname"].encode()).hexdigest(),
        }

        # 組合指紋 = 各 hash 排序後 concat 再 hash
        combined = "|".join(f"{k}={v}" for k, v in sorted(component_hashes.items()))
        fingerprint = hashlib.sha256(combined.encode()).hexdigest()

        return {
            "fingerprint": f"sha256:{fingerprint}",
            "components": components,
            "component_hashes": component_hashes,
        }

    @classmethod
    def get_fingerprint(cls) -> str:
        """只取得最終指紋 hash"""
        return cls.collect()["fingerprint"]

    @classmethod
    def get_component_hashes(cls) -> Dict[str, str]:
        """取得各組件 hash"""
        return cls.collect()["component_hashes"]

    @staticmethod
    def fuzzy_match(expected_hashes: Dict[str, str], actual_hashes: Dict[str, str],
                    threshold: int = 4) -> Tuple[bool, int, List[str]]:
        """
        Fuzzy match: 至少 threshold/5 組件吻合
        Returns: (通過, 吻合數, 不吻合的組件名)
        """
        keys = ["mac", "disk", "cpu", "board", "hostname"]
        matched = 0
        mismatched = []

        for k in keys:
            if expected_hashes.get(k) == actual_hashes.get(k):
                matched += 1
            else:
                mismatched.append(k)

        return matched >= threshold, matched, mismatched


# ═══════════════════════════════════════════════════════════════
# NTP 時間驗證
# ═══════════════════════════════════════════════════════════════
def _query_ntp_time(server: str = "pool.ntp.org", timeout: float = 3.0) -> Optional[float]:
    """查詢 NTP server 取得真實時間 (Unix timestamp)"""
    try:
        NTP_EPOCH = 2208988800  # 1900-01-01 to 1970-01-01
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # NTP request packet (LI=0, VN=3, Mode=3)
        data = b"\x1b" + 47 * b"\0"
        sock.sendto(data, (server, 123))
        data, _ = sock.recvfrom(1024)
        sock.close()
        if len(data) >= 48:
            t = struct.unpack("!I", data[40:44])[0]
            return t - NTP_EPOCH
    except Exception as e:
        logger.debug(f"NTP query failed ({server}): {e}")
    return None


# ═══════════════════════════════════════════════════════════════
# License Manager
# ═══════════════════════════════════════════════════════════════
class LicenseManager:
    _instance: Optional["LicenseManager"] = None
    _REDIS_TS_KEY = "license:last_seen_ts"
    _REDIS_LOCK_KEY = "license:tamper_locked"
    _TIME_DRIFT_TOLERANCE = 300  # 5 分鐘容許偏差

    def __init__(self, license_path: str = "/app/license_dir/license.lic"):
        self.license_path = Path(license_path)
        self._license_data: Optional[Dict[str, Any]] = None
        self._public_key: Optional[Ed25519PublicKey] = None
        self._last_check_result: Optional[LicenseStatus] = None
        self._load_public_key()

    @classmethod
    def get_instance(cls, license_path: str = "/app/license_dir/license.lic") -> "LicenseManager":
        if cls._instance is None:
            cls._instance = cls(license_path)
        return cls._instance

    def _load_public_key(self):
        """載入嵌入的 Ed25519 公鑰"""
        try:
            key = load_pem_public_key(PUBLIC_KEY_PEM)
            if isinstance(key, Ed25519PublicKey):
                self._public_key = key
            else:
                logger.error("Embedded key is not Ed25519")
        except Exception as e:
            logger.error(f"Failed to load public key: {e}")

    def load_license(self) -> Optional[Dict[str, Any]]:
        """從檔案載入 license"""
        if not self.license_path.exists():
            logger.warning(f"License file not found: {self.license_path}")
            return None

        try:
            raw = self.license_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._license_data = data
            return data
        except Exception as e:
            logger.error(f"Failed to load license: {e}")
            return None

    def verify_signature(self, data: Dict[str, Any]) -> bool:
        """驗證 Ed25519 簽章"""
        if not self._public_key:
            logger.error("No public key available")
            return False

        signature_b64 = data.get("signature", "")
        if not signature_b64:
            return False

        try:
            signature = base64.b64decode(signature_b64)
        except Exception:
            return False

        # 簽章覆蓋的 payload = license 去掉 signature 欄位
        payload = {k: v for k, v in data.items() if k != "signature"}
        payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")

        try:
            self._public_key.verify(signature, payload_bytes)
            return True
        except InvalidSignature:
            logger.warning("License signature verification failed")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

    def _get_redis(self):
        """取得 Redis client"""
        try:
            from app.redis.state import _redis
            return _redis
        except Exception:
            return None

    def _check_time_tampering(self, now_ts: float) -> bool:
        """
        偵測系統時間是否被竄改
        Returns True if time is valid, False if tampering detected
        """
        r = self._get_redis()
        if not r:
            return True  # Redis 不可用時不阻擋

        try:
            # 檢查是否已被標記為鎖定
            if r.get(self._REDIS_LOCK_KEY):
                logger.warning("License tamper lock is active")
                return False

            # 取得上次檢查的時間戳
            last_ts_raw = r.get(self._REDIS_TS_KEY)
            if last_ts_raw:
                last_ts = float(last_ts_raw)
                # 若系統時間比上次記錄早超過容許偏差，視為竄改
                if now_ts < last_ts - self._TIME_DRIFT_TOLERANCE:
                    logger.warning(
                        f"Time tampering detected! now={now_ts:.0f}, "
                        f"last_seen={last_ts:.0f}, diff={last_ts - now_ts:.0f}s"
                    )
                    # 鎖定，需要管理員手動解除
                    r.set(self._REDIS_LOCK_KEY, "1")
                    return False

            # 更新 last_seen_ts（只往前不往後）
            r.set(self._REDIS_TS_KEY, str(now_ts))
            return True

        except Exception as e:
            logger.warning(f"Time tamper check error: {e}")
            return True  # 錯誤時不阻擋

    def _ntp_time_check(self, system_ts: float) -> bool:
        """用 NTP 驗證系統時間是否合理"""
        ntp_ts = _query_ntp_time()
        if ntp_ts is None:
            return True  # NTP 不可用時不阻擋 (離線環境)

        drift = abs(system_ts - ntp_ts)
        if drift > self._TIME_DRIFT_TOLERANCE:
            logger.warning(
                f"System time significantly differs from NTP! "
                f"system={system_ts:.0f}, ntp={ntp_ts:.0f}, drift={drift:.0f}s"
            )
            return False
        return True

    def _record_check_to_db(self, status: str, now_ts: float):
        """記錄 license 檢查到 DB (防止 Redis 被清時仍有記錄)"""
        try:
            from app.db.session import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                # Auto-create table if not exists
                db.execute(text(
                    "CREATE TABLE IF NOT EXISTS license_checks ("
                    "  id SERIAL PRIMARY KEY,"
                    "  checked_at TIMESTAMP DEFAULT NOW(),"
                    "  status VARCHAR(32),"
                    "  system_ts DOUBLE PRECISION"
                    ")"
                ))
                db.execute(text(
                    "INSERT INTO license_checks (checked_at, status, system_ts) "
                    "VALUES (NOW(), :status, :ts)"
                ), {"status": status, "ts": now_ts})
                db.commit()
            finally:
                db.close()
        except Exception:
            pass  # DB 記錄是 best-effort

    def check_status(self, skip_ntp: bool = False) -> LicenseStatus:
        """
        完整的授權狀態檢查
        1. 載入 license
        2. 驗證簽章
        3. 驗證硬體指紋
        4. 防時間竄改
        5. 檢查到期日
        """
        now_ts = time.time()

        # 1. 載入
        data = self.load_license()
        if not data:
            self._last_check_result = LicenseStatus.INVALID
            return LicenseStatus.INVALID

        # 2. 驗簽章
        if not self.verify_signature(data):
            self._last_check_result = LicenseStatus.INVALID
            return LicenseStatus.INVALID

        # 3. 驗硬體指紋
        expected_hashes = data.get("component_hashes")
        if expected_hashes:
            actual_hashes = HardwareFingerprint.get_component_hashes()
            passed, matched, mismatched = HardwareFingerprint.fuzzy_match(
                expected_hashes, actual_hashes
            )
            if not passed:
                logger.warning(
                    f"Hardware fingerprint mismatch! "
                    f"matched={matched}/5, mismatched={mismatched}"
                )
                self._last_check_result = LicenseStatus.INVALID
                return LicenseStatus.INVALID

        # 4. 防時間竄改
        if not self._check_time_tampering(now_ts):
            self._last_check_result = LicenseStatus.TAMPERED
            return LicenseStatus.TAMPERED

        if not skip_ntp and not self._ntp_time_check(now_ts):
            self._last_check_result = LicenseStatus.TAMPERED
            return LicenseStatus.TAMPERED

        # 5. 檢查到期日
        now_dt = datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc)

        full_expiry_str = data.get("full_expiry", "")
        history_expiry_str = data.get("history_expiry", "")

        try:
            full_expiry = datetime.datetime.fromisoformat(full_expiry_str)
            if full_expiry.tzinfo is None:
                full_expiry = full_expiry.replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            self._last_check_result = LicenseStatus.INVALID
            return LicenseStatus.INVALID

        try:
            history_expiry = datetime.datetime.fromisoformat(history_expiry_str)
            if history_expiry.tzinfo is None:
                history_expiry = history_expiry.replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            history_expiry = full_expiry  # 沒有 history_expiry 就和 full_expiry 同

        # 判斷狀態
        if now_dt < full_expiry:
            status = LicenseStatus.ACTIVE
        elif now_dt < history_expiry:
            status = LicenseStatus.HISTORY_ONLY
        else:
            status = LicenseStatus.EXPIRED

        self._last_check_result = status

        # 記錄到 DB (best-effort)
        self._record_check_to_db(status.value, now_ts)

        return status

    @property
    def last_result(self) -> Optional[LicenseStatus]:
        return self._last_check_result

    def get_license_info(self) -> Dict[str, Any]:
        """取得 license 摘要（不含簽章）"""
        if self._license_data:
            return {
                "customer": self._license_data.get("customer", ""),
                "full_expiry": self._license_data.get("full_expiry", ""),
                "history_expiry": self._license_data.get("history_expiry", ""),
                "issued_at": self._license_data.get("issued_at", ""),
            }
        return {}
