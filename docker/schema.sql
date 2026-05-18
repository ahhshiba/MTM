--
-- PostgreSQL database dump
--

\restrict VdNeT8VFIZcBX996NUtVhsRDgQPUazjiKeA8Bop5Ozvfn0dEZj1YiiumdawvFlN

-- Dumped from database version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 18.0

-- Started on 2026-02-08 11:29:32

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 866 (class 1247 OID 16420)
-- Name: chat_role; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.chat_role AS ENUM (
    'system',
    'user',
    'assistant'
);


ALTER TYPE public.chat_role OWNER TO postgres;

--
-- TOC entry 860 (class 1247 OID 16390)
-- Name: document_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.document_status AS ENUM (
    'uploaded',
    'ocr_processing',
    'ocr_done',
    'vlm_review',
    'structuring',
    'done',
    'canceled',
    'error'
);


ALTER TYPE public.document_status OWNER TO postgres;

--
-- TOC entry 863 (class 1247 OID 16408)
-- Name: run_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.run_status AS ENUM (
    'queued',
    'running',
    'succeeded',
    'failed',
    'canceled'
);


ALTER TYPE public.run_status OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 217 (class 1259 OID 16440)
-- Name: document_versions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.document_versions (
    id bigint NOT NULL,
    document_id character varying(64) NOT NULL,
    version_no integer NOT NULL,
    label text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.document_versions OWNER TO postgres;

--
-- TOC entry 216 (class 1259 OID 16439)
-- Name: document_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.document_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.document_versions_id_seq OWNER TO postgres;

--
-- TOC entry 3572 (class 0 OID 0)
-- Dependencies: 216
-- Name: document_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.document_versions_id_seq OWNED BY public.document_versions.id;


--
-- TOC entry 215 (class 1259 OID 16427)
-- Name: documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.documents (
    id character varying(64) NOT NULL,
    title text,
    file_path text NOT NULL,
    page_count integer NOT NULL,
    status public.document_status DEFAULT 'uploaded'::public.document_status NOT NULL,
    error_reason text,
    owner_user_id character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.documents OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 16606)
-- Name: exports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.exports (
    id character varying(64) NOT NULL,
    document_id character varying(64) NOT NULL,
    document_version_id bigint NOT NULL,
    format text NOT NULL,
    file_path text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.exports OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 24641)
-- Name: extraction_llm_calls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.extraction_llm_calls (
    id integer NOT NULL,
    extraction_run_id integer,
    call_type character varying NOT NULL,
    prompt text,
    response text,
    image_path text,
    prompt_tokens integer,
    candidate_tokens integer,
    total_tokens integer,
    duration_ms integer,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.extraction_llm_calls OWNER TO postgres;

--
-- TOC entry 234 (class 1259 OID 24640)
-- Name: extraction_llm_calls_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.extraction_llm_calls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.extraction_llm_calls_id_seq OWNER TO postgres;

--
-- TOC entry 3573 (class 0 OID 0)
-- Dependencies: 234
-- Name: extraction_llm_calls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.extraction_llm_calls_id_seq OWNED BY public.extraction_llm_calls.id;


--
-- TOC entry 233 (class 1259 OID 24617)
-- Name: extraction_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.extraction_runs (
    id integer NOT NULL,
    ocr_run_id integer,
    document_id character varying NOT NULL,
    status character varying DEFAULT 'pending'::character varying NOT NULL,
    model character varying DEFAULT 'gemini-2.5-flash'::character varying,
    mode character varying DEFAULT 'auto'::character varying,
    total_prompt_tokens integer DEFAULT 0,
    total_candidate_tokens integer DEFAULT 0,
    total_tokens integer DEFAULT 0,
    raw_result_path text,
    structured_result_path text,
    bbox_result_path text,
    error_message text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.extraction_runs OWNER TO postgres;

--
-- TOC entry 232 (class 1259 OID 24616)
-- Name: extraction_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.extraction_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.extraction_runs_id_seq OWNER TO postgres;

--
-- TOC entry 3574 (class 0 OID 0)
-- Dependencies: 232
-- Name: extraction_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.extraction_runs_id_seq OWNED BY public.extraction_runs.id;


--
-- TOC entry 224 (class 1259 OID 16525)
-- Name: images; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.images (
    id character varying(64) NOT NULL,
    ocr_run_id bigint NOT NULL,
    page_id bigint NOT NULL,
    bbox_json jsonb NOT NULL,
    image_path text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.images OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 16627)
-- Name: images_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.images_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.images_id_seq OWNER TO postgres;

--
-- TOC entry 3575 (class 0 OID 0)
-- Dependencies: 231
-- Name: images_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.images_id_seq OWNED BY public.images.id;


--
-- TOC entry 221 (class 1259 OID 16479)
-- Name: ocr_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ocr_runs (
    id bigint NOT NULL,
    document_id character varying(64) NOT NULL,
    document_version_id bigint NOT NULL,
    status public.run_status DEFAULT 'queued'::public.run_status NOT NULL,
    engine text DEFAULT 'paddleocr-vl'::text NOT NULL,
    options_json jsonb,
    output_dir_path text NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    error_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    job_id character varying(64),
    output_dir text,
    error_code character varying(64),
    error_message text,
    updated_at timestamp with time zone
);


ALTER TABLE public.ocr_runs OWNER TO postgres;

--
-- TOC entry 220 (class 1259 OID 16478)
-- Name: ocr_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ocr_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ocr_runs_id_seq OWNER TO postgres;

--
-- TOC entry 3576 (class 0 OID 0)
-- Dependencies: 220
-- Name: ocr_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ocr_runs_id_seq OWNED BY public.ocr_runs.id;


--
-- TOC entry 223 (class 1259 OID 16503)
-- Name: page_ocr_artifacts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.page_ocr_artifacts (
    id bigint NOT NULL,
    ocr_run_id bigint NOT NULL,
    page_id bigint NOT NULL,
    result_json_path text,
    result_md_path text,
    vis_image_path text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.page_ocr_artifacts OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 16502)
-- Name: page_ocr_artifacts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.page_ocr_artifacts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.page_ocr_artifacts_id_seq OWNER TO postgres;

--
-- TOC entry 3577 (class 0 OID 0)
-- Dependencies: 222
-- Name: page_ocr_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.page_ocr_artifacts_id_seq OWNED BY public.page_ocr_artifacts.id;


--
-- TOC entry 219 (class 1259 OID 16458)
-- Name: pages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pages (
    id bigint NOT NULL,
    document_id character varying(64) NOT NULL,
    page_no integer NOT NULL,
    render_image_path text,
    is_reviewed boolean DEFAULT false NOT NULL,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.pages OWNER TO postgres;

--
-- TOC entry 218 (class 1259 OID 16457)
-- Name: pages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pages_id_seq OWNER TO postgres;

--
-- TOC entry 3578 (class 0 OID 0)
-- Dependencies: 218
-- Name: pages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pages_id_seq OWNED BY public.pages.id;


--
-- TOC entry 229 (class 1259 OID 16581)
-- Name: structure_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.structure_runs (
    id bigint NOT NULL,
    document_id character varying(64) NOT NULL,
    document_version_id bigint NOT NULL,
    status public.run_status DEFAULT 'queued'::public.run_status NOT NULL,
    engine text DEFAULT 'llm'::text NOT NULL,
    options_json jsonb,
    input_snapshot_path text,
    output_json_path text NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    error_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.structure_runs OWNER TO postgres;

--
-- TOC entry 228 (class 1259 OID 16580)
-- Name: structure_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.structure_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.structure_runs_id_seq OWNER TO postgres;

--
-- TOC entry 3579 (class 0 OID 0)
-- Dependencies: 228
-- Name: structure_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.structure_runs_id_seq OWNED BY public.structure_runs.id;


--
-- TOC entry 227 (class 1259 OID 16565)
-- Name: vlm_messages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vlm_messages (
    id bigint NOT NULL,
    session_id character varying(64) NOT NULL,
    role public.chat_role NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    response_json jsonb,
    prompt_tokens integer,
    candidate_tokens integer,
    total_tokens integer
);


ALTER TABLE public.vlm_messages OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 16564)
-- Name: vlm_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.vlm_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.vlm_messages_id_seq OWNER TO postgres;

--
-- TOC entry 3580 (class 0 OID 0)
-- Dependencies: 226
-- Name: vlm_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.vlm_messages_id_seq OWNED BY public.vlm_messages.id;


--
-- TOC entry 225 (class 1259 OID 16546)
-- Name: vlm_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vlm_sessions (
    id character varying(64) NOT NULL,
    image_id character varying(64) NOT NULL,
    model text DEFAULT 'gemini'::text NOT NULL,
    system_prompt text,
    finalized boolean DEFAULT false NOT NULL,
    finalized_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    aux_image_path text
);


ALTER TABLE public.vlm_sessions OWNER TO postgres;

--
-- TOC entry 3319 (class 2604 OID 16443)
-- Name: document_versions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_versions ALTER COLUMN id SET DEFAULT nextval('public.document_versions_id_seq'::regclass);


--
-- TOC entry 3354 (class 2604 OID 24644)
-- Name: extraction_llm_calls id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_llm_calls ALTER COLUMN id SET DEFAULT nextval('public.extraction_llm_calls_id_seq'::regclass);


--
-- TOC entry 3345 (class 2604 OID 24620)
-- Name: extraction_runs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_runs ALTER COLUMN id SET DEFAULT nextval('public.extraction_runs_id_seq'::regclass);


--
-- TOC entry 3331 (class 2604 OID 16628)
-- Name: images id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images ALTER COLUMN id SET DEFAULT nextval('public.images_id_seq'::regclass);


--
-- TOC entry 3325 (class 2604 OID 16482)
-- Name: ocr_runs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ocr_runs ALTER COLUMN id SET DEFAULT nextval('public.ocr_runs_id_seq'::regclass);


--
-- TOC entry 3329 (class 2604 OID 16506)
-- Name: page_ocr_artifacts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.page_ocr_artifacts ALTER COLUMN id SET DEFAULT nextval('public.page_ocr_artifacts_id_seq'::regclass);


--
-- TOC entry 3321 (class 2604 OID 16461)
-- Name: pages id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pages ALTER COLUMN id SET DEFAULT nextval('public.pages_id_seq'::regclass);


--
-- TOC entry 3340 (class 2604 OID 16584)
-- Name: structure_runs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.structure_runs ALTER COLUMN id SET DEFAULT nextval('public.structure_runs_id_seq'::regclass);


--
-- TOC entry 3338 (class 2604 OID 16568)
-- Name: vlm_messages id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vlm_messages ALTER COLUMN id SET DEFAULT nextval('public.vlm_messages_id_seq'::regclass);


--
-- TOC entry 3361 (class 2606 OID 16450)
-- Name: document_versions document_versions_document_id_version_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_document_id_version_no_key UNIQUE (document_id, version_no);


--
-- TOC entry 3363 (class 2606 OID 16448)
-- Name: document_versions document_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_pkey PRIMARY KEY (id);


--
-- TOC entry 3357 (class 2606 OID 16436)
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- TOC entry 3399 (class 2606 OID 16613)
-- Name: exports exports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.exports
    ADD CONSTRAINT exports_pkey PRIMARY KEY (id);


--
-- TOC entry 3406 (class 2606 OID 24649)
-- Name: extraction_llm_calls extraction_llm_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_llm_calls
    ADD CONSTRAINT extraction_llm_calls_pkey PRIMARY KEY (id);


--
-- TOC entry 3402 (class 2606 OID 24632)
-- Name: extraction_runs extraction_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 3384 (class 2606 OID 16533)
-- Name: images images_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_pkey PRIMARY KEY (id);


--
-- TOC entry 3375 (class 2606 OID 16489)
-- Name: ocr_runs ocr_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ocr_runs
    ADD CONSTRAINT ocr_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 3378 (class 2606 OID 16513)
-- Name: page_ocr_artifacts page_ocr_artifacts_ocr_run_id_page_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.page_ocr_artifacts
    ADD CONSTRAINT page_ocr_artifacts_ocr_run_id_page_id_key UNIQUE (ocr_run_id, page_id);


--
-- TOC entry 3380 (class 2606 OID 16511)
-- Name: page_ocr_artifacts page_ocr_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.page_ocr_artifacts
    ADD CONSTRAINT page_ocr_artifacts_pkey PRIMARY KEY (id);


--
-- TOC entry 3368 (class 2606 OID 16470)
-- Name: pages pages_document_id_page_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_document_id_page_no_key UNIQUE (document_id, page_no);


--
-- TOC entry 3370 (class 2606 OID 16468)
-- Name: pages pages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);


--
-- TOC entry 3395 (class 2606 OID 16593)
-- Name: structure_runs structure_runs_document_version_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.structure_runs
    ADD CONSTRAINT structure_runs_document_version_id_key UNIQUE (document_version_id);


--
-- TOC entry 3397 (class 2606 OID 16591)
-- Name: structure_runs structure_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.structure_runs
    ADD CONSTRAINT structure_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 3391 (class 2606 OID 16573)
-- Name: vlm_messages vlm_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vlm_messages
    ADD CONSTRAINT vlm_messages_pkey PRIMARY KEY (id);


--
-- TOC entry 3388 (class 2606 OID 16556)
-- Name: vlm_sessions vlm_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vlm_sessions
    ADD CONSTRAINT vlm_sessions_pkey PRIMARY KEY (id);


--
-- TOC entry 3364 (class 1259 OID 16456)
-- Name: idx_doc_versions_document; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_doc_versions_document ON public.document_versions USING btree (document_id, version_no DESC);


--
-- TOC entry 3358 (class 1259 OID 16438)
-- Name: idx_documents_owner_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_documents_owner_created ON public.documents USING btree (owner_user_id, created_at DESC);


--
-- TOC entry 3359 (class 1259 OID 16437)
-- Name: idx_documents_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_documents_status ON public.documents USING btree (status);


--
-- TOC entry 3400 (class 1259 OID 16624)
-- Name: idx_exports_document; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_exports_document ON public.exports USING btree (document_id, document_version_id, created_at DESC);


--
-- TOC entry 3407 (class 1259 OID 24655)
-- Name: idx_extraction_llm_calls_run_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_extraction_llm_calls_run_id ON public.extraction_llm_calls USING btree (extraction_run_id);


--
-- TOC entry 3403 (class 1259 OID 24639)
-- Name: idx_extraction_runs_document_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_extraction_runs_document_id ON public.extraction_runs USING btree (document_id);


--
-- TOC entry 3404 (class 1259 OID 24638)
-- Name: idx_extraction_runs_ocr_run_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_extraction_runs_ocr_run_id ON public.extraction_runs USING btree (ocr_run_id);


--
-- TOC entry 3381 (class 1259 OID 16545)
-- Name: idx_images_ocr_run; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_images_ocr_run ON public.images USING btree (ocr_run_id);


--
-- TOC entry 3382 (class 1259 OID 16544)
-- Name: idx_images_page; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_images_page ON public.images USING btree (page_id, sort_order);


--
-- TOC entry 3371 (class 1259 OID 16500)
-- Name: idx_ocr_runs_doc_ver; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ocr_runs_doc_ver ON public.ocr_runs USING btree (document_id, document_version_id);


--
-- TOC entry 3372 (class 1259 OID 16626)
-- Name: idx_ocr_runs_job_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ocr_runs_job_id ON public.ocr_runs USING btree (job_id);


--
-- TOC entry 3373 (class 1259 OID 16501)
-- Name: idx_ocr_runs_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ocr_runs_status ON public.ocr_runs USING btree (status);


--
-- TOC entry 3376 (class 1259 OID 16524)
-- Name: idx_page_artifacts_run; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_page_artifacts_run ON public.page_ocr_artifacts USING btree (ocr_run_id);


--
-- TOC entry 3365 (class 1259 OID 16476)
-- Name: idx_pages_document; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pages_document ON public.pages USING btree (document_id, page_no);


--
-- TOC entry 3366 (class 1259 OID 16477)
-- Name: idx_pages_reviewed; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pages_reviewed ON public.pages USING btree (document_id, is_reviewed);


--
-- TOC entry 3392 (class 1259 OID 16604)
-- Name: idx_structure_runs_doc_ver; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_structure_runs_doc_ver ON public.structure_runs USING btree (document_id, document_version_id);


--
-- TOC entry 3393 (class 1259 OID 16605)
-- Name: idx_structure_runs_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_structure_runs_status ON public.structure_runs USING btree (status);


--
-- TOC entry 3389 (class 1259 OID 16579)
-- Name: idx_vlm_messages_session; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_vlm_messages_session ON public.vlm_messages USING btree (session_id, created_at);


--
-- TOC entry 3385 (class 1259 OID 16563)
-- Name: idx_vlm_sessions_finalized; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_vlm_sessions_finalized ON public.vlm_sessions USING btree (finalized);


--
-- TOC entry 3386 (class 1259 OID 16562)
-- Name: idx_vlm_sessions_image; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_vlm_sessions_image ON public.vlm_sessions USING btree (image_id, created_at DESC);


--
-- TOC entry 3408 (class 2606 OID 16451)
-- Name: document_versions document_versions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.document_versions
    ADD CONSTRAINT document_versions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 3420 (class 2606 OID 16614)
-- Name: exports exports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.exports
    ADD CONSTRAINT exports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 3421 (class 2606 OID 16619)
-- Name: exports exports_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.exports
    ADD CONSTRAINT exports_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- TOC entry 3423 (class 2606 OID 24650)
-- Name: extraction_llm_calls extraction_llm_calls_extraction_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_llm_calls
    ADD CONSTRAINT extraction_llm_calls_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES public.extraction_runs(id) ON DELETE CASCADE;


--
-- TOC entry 3422 (class 2606 OID 24633)
-- Name: extraction_runs extraction_runs_ocr_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_ocr_run_id_fkey FOREIGN KEY (ocr_run_id) REFERENCES public.ocr_runs(id) ON DELETE CASCADE;


--
-- TOC entry 3414 (class 2606 OID 16534)
-- Name: images images_ocr_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_ocr_run_id_fkey FOREIGN KEY (ocr_run_id) REFERENCES public.ocr_runs(id) ON DELETE CASCADE;


--
-- TOC entry 3415 (class 2606 OID 16539)
-- Name: images images_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- TOC entry 3410 (class 2606 OID 16490)
-- Name: ocr_runs ocr_runs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ocr_runs
    ADD CONSTRAINT ocr_runs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 3411 (class 2606 OID 16495)
-- Name: ocr_runs ocr_runs_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ocr_runs
    ADD CONSTRAINT ocr_runs_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- TOC entry 3412 (class 2606 OID 16514)
-- Name: page_ocr_artifacts page_ocr_artifacts_ocr_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.page_ocr_artifacts
    ADD CONSTRAINT page_ocr_artifacts_ocr_run_id_fkey FOREIGN KEY (ocr_run_id) REFERENCES public.ocr_runs(id) ON DELETE CASCADE;


--
-- TOC entry 3413 (class 2606 OID 16519)
-- Name: page_ocr_artifacts page_ocr_artifacts_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.page_ocr_artifacts
    ADD CONSTRAINT page_ocr_artifacts_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- TOC entry 3409 (class 2606 OID 16471)
-- Name: pages pages_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 3418 (class 2606 OID 16594)
-- Name: structure_runs structure_runs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.structure_runs
    ADD CONSTRAINT structure_runs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 3419 (class 2606 OID 16599)
-- Name: structure_runs structure_runs_document_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.structure_runs
    ADD CONSTRAINT structure_runs_document_version_id_fkey FOREIGN KEY (document_version_id) REFERENCES public.document_versions(id) ON DELETE CASCADE;


--
-- TOC entry 3417 (class 2606 OID 16574)
-- Name: vlm_messages vlm_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vlm_messages
    ADD CONSTRAINT vlm_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.vlm_sessions(id) ON DELETE CASCADE;


--
-- TOC entry 3416 (class 2606 OID 16557)
-- Name: vlm_sessions vlm_sessions_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vlm_sessions
    ADD CONSTRAINT vlm_sessions_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(id) ON DELETE CASCADE;


-- Completed on 2026-02-08 11:29:37

--
-- PostgreSQL database dump complete
--

\unrestrict VdNeT8VFIZcBX996NUtVhsRDgQPUazjiKeA8Bop5Ozvfn0dEZj1YiiumdawvFlN

