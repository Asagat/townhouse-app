--
-- PostgreSQL database dump
--

\restrict febh1LZq2YsR4I3ABmGfhuNKLgkOckaNMb9TmgXqUn1idVughfAzjLQWMIdOxiy

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

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
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, password_hash, full_name, role, is_active, created_at, updated_at, account_id) FROM stdin;
1	migration	260000$ca93d50ffadd260f8ce55abac8a44bf9$47349dfaa7b0b4bc0e8a23de8839d2a0c2bb4fe9f015dd3fa94712edbe928a53	Миграция (системный)	admin	f	2026-09-03 11:49:26.5841	2026-09-03 11:49:26.5841	\N
2	admin	260000$ef52679f48619af2a07a6a7a743395fd$a9752ed78bade71417f9133a742582b53e5a75df04d9b48257f1ee4242ba974a		admin	t	2026-09-03 13:44:30.265095	2026-09-03 13:44:30.265095	\N
\.


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 88, true);


--
-- PostgreSQL database dump complete
--

\unrestrict febh1LZq2YsR4I3ABmGfhuNKLgkOckaNMb9TmgXqUn1idVughfAzjLQWMIdOxiy

