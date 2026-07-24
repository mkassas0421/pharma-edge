"""Seed the database with an initial set of tracked tickers and mock catalyst events."""

import datetime
from sqlalchemy.orm import Session

from app.models.database import Ticker, CatalystEvent


SEED_TICKERS = [
    # ── Large-cap Biotech ──
    {"ticker": "AMGN", "company_name": "Amgen Inc.", "sector": "Large-cap Biotech"},
    {"ticker": "BIIB", "company_name": "Biogen Inc.", "sector": "Large-cap Biotech"},
    {"ticker": "GILD", "company_name": "Gilead Sciences", "sector": "Large-cap Biotech"},
    {"ticker": "MRNA", "company_name": "Moderna Inc.", "sector": "Large-cap Biotech"},
    {"ticker": "REGN", "company_name": "Regeneron Pharmaceuticals", "sector": "Large-cap Biotech"},
    {"ticker": "VRTX", "company_name": "Vertex Pharmaceuticals", "sector": "Large-cap Biotech"},
    {"ticker": "SNY", "company_name": "Sanofi S.A.", "sector": "Large-cap Biotech"},
    {"ticker": "AZN", "company_name": "AstraZeneca PLC", "sector": "Large-cap Biotech"},

    # ── Mid-cap Biotech ──
    {"ticker": "ALKS", "company_name": "Alkermes PLC", "sector": "Mid-cap Biotech"},
    {"ticker": "BMRN", "company_name": "BioMarin Pharmaceutical", "sector": "Mid-cap Biotech"},
    {"ticker": "CRSP", "company_name": "CRISPR Therapeutics", "sector": "Mid-cap Biotech"},
    {"ticker": "EXEL", "company_name": "Exelixis Inc.", "sector": "Mid-cap Biotech"},
    {"ticker": "NTLA", "company_name": "Intellia Therapeutics", "sector": "Mid-cap Biotech"},
    {"ticker": "SRPT", "company_name": "Sarepta Therapeutics", "sector": "Mid-cap Biotech"},
    {"ticker": "UTHR", "company_name": "United Therapeutics", "sector": "Mid-cap Biotech"},
    {"ticker": "BGNE", "company_name": "BeiGene Ltd.", "sector": "Mid-cap Biotech"},

    # ── Small-cap / Micro-cap Pharma ──
    {"ticker": "ACAD", "company_name": "ACADIA Pharmaceuticals", "sector": "Small-cap Biotech"},
    {"ticker": "ALLO", "company_name": "Allogene Therapeutics", "sector": "Small-cap Biotech"},
    {"ticker": "BEAM", "company_name": "Beam Therapeutics", "sector": "Small-cap Biotech"},
    {"ticker": "EDIT", "company_name": "Editas Medicine", "sector": "Micro-cap Pharma"},
    {"ticker": "FATE", "company_name": "Fate Therapeutics", "sector": "Small-cap Biotech"},
    {"ticker": "RXRX", "company_name": "Recursion Pharmaceuticals", "sector": "Small-cap Biotech"},
    {"ticker": "RCKT", "company_name": "Rocket Pharmaceuticals", "sector": "Small-cap Biotech"},
    {"ticker": "VERV", "company_name": "Verve Therapeutics", "sector": "Small-cap Biotech"},
    {"ticker": "CRBU", "company_name": "Caribou Biosciences", "sector": "Micro-cap Pharma"},
    {"ticker": "DNLI", "company_name": "Denali Therapeutics", "sector": "Mid-cap Biotech"},
    {"ticker": "KURA", "company_name": "Kura Oncology", "sector": "Small-cap Biotech"},
    {"ticker": "RCUS", "company_name": "Arcus Biosciences", "sector": "Small-cap Biotech"},
    {"ticker": "KYMR", "company_name": "Kymera Therapeutics", "sector": "Small-cap Biotech"},
    {"ticker": "NBIX", "company_name": "Neurocrine Biosciences", "sector": "Mid-cap Biotech"},
    {"ticker": "IONS", "company_name": "Ionis Pharmaceuticals", "sector": "Mid-cap Biotech"},
]

SEED_EVENTS = [
    # ── July 2026 ──
    {
        "ticker": "NBIX",
        "title": "PDUFA date — crinecerfont (congenital adrenal hyperplasia)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 7, 26, 0, 0),
        "impact_level": "High",
        "drug_name": "Crinecerfont (NBI-74788)",
        "mechanism": "CRF1 receptor antagonist — reduces ACTH-driven androgen overproduction",
        "trial_phase": "Phase 3",
        "trial_name": "CAHptain-1 (pediatric) / CAHptain-2 (adult)",
        "milestone": "PDUFA date — FDA decision on NDA approval",
        "background": (
            "Crinecerfont is a first-in-class oral CRF1 receptor antagonist being developed for "
            "congenital adrenal hyperplasia (CAH), a rare genetic disorder causing cortisol deficiency "
            "and androgen excess. Current standard of care is high-dose glucocorticoids with serious "
            "long-term side effects. In Phase 3, crinecerfont demonstrated significant reduction in "
            "androstenedione levels while allowing patients to reduce their glucocorticoid dose by "
            "25–50%. If approved, it would be the first non-steroidal treatment for CAH in decades. "
            "The FDA granted Breakthrough Therapy designation."
        ),
    },
    {
        "ticker": "VRTX",
        "title": "FDA Advisory Committee — VX-548 (acute pain)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 7, 30, 0, 0),
        "impact_level": "High",
        "drug_name": "Suzetrigine (VX-548)",
        "mechanism": "NaV1.8 inhibitor — non-opioid pain signal blocker in peripheral neurons",
        "trial_phase": "Phase 3",
        "trial_name": "PROACT 1 & 2 (abdominoplasty), PROACT 3 (bunionectomy)",
        "milestone": "FDA Advisory Committee meeting before PDUFA decision",
        "background": (
            "VX-548 is Vertex's lead non-opioid painkiller targeting NaV1.8, a sodium channel "
            "expressed exclusively in peripheral pain-sensing neurons. In Phase 3 trials, it met "
            "its primary endpoint of reduced pain over 48 hours post-surgery with statistical "
            "significance, though the effect size versus placebo was modest. The key advantage: "
            "no abuse potential, no respiratory depression, and no euphoria — making it a "
            "potentially Schedule-IV-or-lower analgesic. The AdCom vote will be closely watched "
            "as this is the most advanced non-opioid pain candidate in decades. FDA decision date "
            "is January 2027, but the AdCom signal drives the stock."
        ),
    },

    # ── August 2026 ──
    {
        "ticker": "GILD",
        "title": "Phase 3 readout — lenacapavir (HIV pre-exposure prophylaxis)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 8, 5, 0, 0),
        "impact_level": "High",
        "drug_name": "Lenacapavir (GS-6207)",
        "mechanism": "HIV-1 capsid inhibitor — disrupts multiple stages of viral replication",
        "trial_phase": "Phase 3",
        "trial_name": "PURPOSE 1 (cisgender women), PURPOSE 2 (men who have sex with men)",
        "milestone": "Top-line efficacy data for twice-yearly injectable PrEP",
        "background": (
            "Lenacapavir is a first-in-class HIV capsid inhibitor already approved for treatment-resistant "
            "HIV as a twice-yearly injectable. Gilead is now repurposing it for PrEP (pre-exposure "
            "prophylaxis) — a market currently dominated by daily oral pills like Truvada and Descovy. "
            "PURPOSE 1 showed 100% efficacy in cisgender women. PURPOSE 2 is the pivotal trial for "
            "men, and positive data would position lenacapavir as the first injectable PrEP requiring "
            "only two doses per year — a massive potential market. This is Gilead's single most "
            "important pipeline catalyst."
        ),
    },
    {
        "ticker": "SRPT",
        "title": "Phase 2 readout — SRP-9001 (Duchenne gene therapy)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 8, 10, 0, 0),
        "impact_level": "Medium",
        "drug_name": "SRP-9001 (Elevidys + next-gen)",
        "mechanism": "AAV-mediated micro-dystrophin gene replacement therapy",
        "trial_phase": "Phase 2",
        "trial_name": "ENVISION (pivotal Phase 3) follow-up / EMBARK cohort extension",
        "milestone": "Updated functional data in ambulatory DMD patients",
        "background": (
            "Elevidys was the first approved gene therapy for Duchenne muscular dystrophy (DMD), "
            "but with accelerated approval and conflicting efficacy data. The EMBARK Phase 3 trial "
            "missed its primary endpoint (NSAA) in the full population but showed benefit in "
            "younger patients. This update will show longer-term functional data from the "
            "extension study. Sarepta is also developing a next-gen version with improved capsid "
            "design. The stock is highly binary on every data release as DMD is a massive "
            "unmet-need market with no curative options beyond Elevidys."
        ),
    },
    {
        "ticker": "CRBU",
        "title": "Phase 1 update — CB-010 (relapsed/refractory DLBCL)",
        "event_type": "PHASE1_READOUT",
        "event_date": datetime.datetime(2026, 8, 15, 0, 0),
        "impact_level": "Low",
        "drug_name": "CB-010",
        "mechanism": "Allogeneic anti-CD19 CAR-T with PD-1 knockout via CRISPR editing",
        "trial_phase": "Phase 1",
        "trial_name": "ANTLER study",
        "milestone": "Initial safety and efficacy update in DLBCL patients",
        "background": (
            "CB-010 is Caribou's lead allogeneic CAR-T therapy for relapsed/refractory diffuse "
            "large B-cell lymphoma (DLBCL). It uses CRISPR-edited healthy donor T cells with an "
            "anti-CD19 CAR plus PD-1 knockout for enhanced persistence. This update will show "
            "response rates and durability from the ongoing Phase 1 ANTLER trial. As a micro-cap "
            "biotech, each data point is significant for Caribou's valuation."
        ),
    },
    {
        "ticker": "BIIB",
        "title": "PDUFA date — Leqembi subcutaneous formulation",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 8, 21, 0, 0),
        "impact_level": "High",
        "drug_name": "Leqembi (lecanemab) subcutaneous",
        "mechanism": "Anti-amyloid beta protofibril monoclonal antibody for Alzheimer's disease",
        "trial_phase": "Phase 3 (subcutaneous formulation)",
        "trial_name": "Clarity AD open-label extension / subcutaneous bioequivalence study",
        "milestone": "FDA decision on SC formulation for at-home administration",
        "background": (
            "Leqembi (lecanemab) is already approved for early Alzheimer's disease via intravenous "
            "infusion every two weeks. This PDUFA covers a subcutaneous auto-injector formulation "
            "that patients could self-administer at home, dramatically expanding accessibility. "
            "The SC formulation showed comparable efficacy and a slightly lower ARIA-E (brain swelling) "
            "rate in bridging studies. Approval would remove the infusion-center bottleneck and "
            "significantly expand the addressable patient population. This is Biogen's most important "
            "near-term catalyst after Leqembi's label expansion."
        ),
    },
    {
        "ticker": "BEAM",
        "title": "Phase 1/2 update — BEAM-101 (sickle cell disease)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 8, 25, 0, 0),
        "impact_level": "Medium",
        "drug_name": "BEAM-101",
        "mechanism": "Base editing therapy to reactivate fetal hemoglobin (HbF) via HBG promoter editing",
        "trial_phase": "Phase 1/2",
        "trial_name": "BEAM-101-001",
        "milestone": "Updated engraftment and fetal hemoglobin induction data",
        "background": (
            "BEAM-101 is Beam Therapeutics' lead in vivo base editing candidate for sickle cell disease. "
            "Instead of cutting DNA like CRISPR-Cas9, base editing chemically converts one DNA base to "
            "another — potentially safer with fewer off-target effects. BEAM-101 edits the HBG promoter "
            "to boost fetal hemoglobin production, mimicking the natural protective effect seen in "
            "patients with hereditary persistence of fetal hemoglobin. This is a competitive space "
            "with CASGEVY already approved, but BEAM-101's differentiated editing approach could "
            "offer better safety and efficacy."
        ),
    },

    # ── September 2026 ──
    {
        "ticker": "ACAD",
        "title": "PDUFA date — pimavanserin (Alzheimer's disease psychosis)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 9, 4, 0, 0),
        "impact_level": "High",
        "drug_name": "Pimavanserin (Nuplazid)",
        "mechanism": "5-HT2A inverse agonist — reduces psychosis without blocking dopamine",
        "trial_phase": "Phase 3",
        "trial_name": "Study 045 / HARMONY",
        "milestone": "FDA decision on sNDA for dementia-related psychosis in Alzheimer's",
        "background": (
            "Pimavanserin is already approved for Parkinson's disease psychosis under the brand "
            "Nuplazid. ACADIA is seeking label expansion to treat psychosis in Alzheimer's disease "
            "patients — a much larger market affecting ~30% of Alzheimer's patients. The Phase 3 "
            "HARMONY study showed significant reduction in psychosis relapse versus placebo. If "
            "approved, this would be the first and only drug for Alzheimer's psychosis. Previous "
            "FDA rejection in 2021 on efficacy concerns was followed by additional data that "
            "ACADIA believes addresses the agency's questions."
        ),
    },
    {
        "ticker": "KYMR",
        "title": "Phase 2 readout — KT-474 (atopic dermatitis)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 9, 8, 0, 0),
        "impact_level": "Medium",
        "drug_name": "KT-474 (SAR444656)",
        "mechanism": "IRAK4 degrader — targeted protein degradation of innate immune signaling",
        "trial_phase": "Phase 2",
        "trial_name": "Atopic dermatitis Phase 2 (partnered with Sanofi)",
        "milestone": "Efficacy and safety data in moderate-to-severe atopic dermatitis",
        "background": (
            "KT-474 is Kymera's lead heterobifunctional degrader that eliminates IRAK4 protein "
            "(rather than just inhibiting it). This is the most advanced targeted protein degradation "
            "program in immunology — a big test for the degrader modality beyond oncology. "
            "Positive Phase 2 data would validate the platform and unlock significant value, "
            "especially with Sanofi as a partner. The atopic dermatitis market is crowded "
            "(Dupixent, JAK inhibitors), so differentiation on safety (no JAK-box warning) "
            "will be key."
        ),
    },
    {
        "ticker": "ALKS",
        "title": "Phase 3 readout — ALKS 2680 (narcolepsy type 1)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 9, 10, 0, 0),
        "impact_level": "Medium",
        "drug_name": "ALKS 2680",
        "mechanism": "Orexin-2 receptor agonist — replaces missing orexin signaling in narcolepsy",
        "trial_phase": "Phase 3",
        "trial_name": "VANILLA-1",
        "milestone": "Top-line efficacy data on wakefulness and cataplexy reduction",
        "background": (
            "ALKS 2680 is Alkermes' orexin-2 receptor agonist for narcolepsy type 1, a condition "
            "caused by loss of orexin-producing neurons. Current treatments (modafinil, "
            "amphetamines, sodium oxybate) address symptoms indirectly with significant side "
            "effects. ALKS 2680 replaces the missing orexin signal directly, potentially offering "
            "better efficacy and tolerability. This is Alkermes' most important pipeline asset "
            "and the orexin agonist class is one of the most anticipated in CNS drug development."
        ),
    },
    {
        "ticker": "RCUS",
        "title": "Phase 2 readout — domvanalimab + zimberelimab (NSCLC)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 9, 14, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Domvanalimab + Zimberelimab",
        "mechanism": "Anti-TIGIT + anti-PD-1 combination immunotherapy",
        "trial_phase": "Phase 2",
        "trial_name": "ARC-10 (first-line NSCLC, PD-L1 high)",
        "milestone": "Updated PFS and OS data in first-line non-small cell lung cancer",
        "background": (
            "Arcus is developing domvanalimab (anti-TIGIT) in combination with zimberelimab "
            "(anti-PD-1) as a potential standard-of-care for first-line NSCLC. The TIGIT/PD-1 "
            "combo space has been controversial after Roche's tiragolumab failures, but Arcus "
            "uses an Fc-silent anti-TIGIT antibody designed to avoid the activation issues that "
            "plagued Roche's candidate. Additional follow-up data from ARC-10 will show whether "
            "the signals from earlier readouts hold. A positive result would position Arcus for "
            "a registration path without needing a partner."
        ),
    },
    {
        "ticker": "AMGN",
        "title": "Phase 3 readout — MariTide (obesity)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 9, 15, 0, 0),
        "impact_level": "High",
        "drug_name": "MariTide (AMG 133)",
        "mechanism": "GLP-1/GIP dual agonist — activates GLP-1, blocks GIP",
        "trial_phase": "Phase 3",
        "trial_name": "MARITIME-1 (obesity without diabetes)",
        "milestone": "Top-line 52-week weight loss data",
        "background": (
            "MariTide is Amgen's entry into the obesity market, differentiated from Novo Nordisk's "
            "Wegovy/Ozempic and Eli Lilly's Zepbound/Mounjaro by a unique mechanism: it agonizes "
            "GLP-1 while antagonizing GIP (competitors agonize both). Early data showed ~14.5% "
            "weight loss at 12 weeks, and the monthly subcutaneous dosing could be a significant "
            "convenience advantage over weekly injections. However, tolerability (nausea/vomiting "
            "rates) and the degree of weight loss at 52 weeks will determine whether MariTide can "
            "compete in the massive obesity market projected to reach $100B+."
        ),
    },
    {
        "ticker": "AZN",
        "title": "Phase 3 readout — datopotamab deruxtecan (NSCLC)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 9, 22, 0, 0),
        "impact_level": "High",
        "drug_name": "Datopotamab deruxtecan (Dato-DXd)",
        "mechanism": "TROP2-directed antibody-drug conjugate with DXd topoisomerase I inhibitor payload",
        "trial_phase": "Phase 3",
        "trial_name": "TROPION-Lung01 (second-line NSCLC)",
        "milestone": "Overall survival data (mature OS readout)",
        "background": (
            "Dato-DXd is a TROP2-directed ADC from the Daiichi Sankyo/AstraZeneca collaboration. "
            "TROPION-Lung01 previously showed statistically significant PFS improvement but the "
            "OS data were immature. This mature OS readout is the binary event: if OS is positive, "
            "Dato-DXd becomes a standard-of-care option in second-line NSCLC and validates the "
            "entire TROP2 ADC class. If OS is negative despite PFS benefit, it would raise "
            "questions about the surrogate endpoint. TROP2 is one of the most contested ADC "
            "targets with multiple competitors including Gilead's Trodelvy."
        ),
    },
    {
        "ticker": "REGN",
        "title": "PDUFA date — odronextamab (relapsed/refractory follicular lymphoma)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 9, 30, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Odronextamab (REGN1979)",
        "mechanism": "CD20 × CD3 bispecific antibody — redirects T cells to kill B cells",
        "trial_phase": "Phase 2 (pivotal)",
        "trial_name": "ELM-2 (follicular lymphoma cohort)",
        "milestone": "FDA decision on BLA for relapsed/refractory FL",
        "background": (
            "Odronextamab is Regeneron's bispecific antibody targeting CD20 on B cells and CD3 on "
            "T cells, bridging them to kill lymphoma cells. This is a competitive space with "
            "Lunsumio (Genentech) and Epkinly (AbbVie) already approved. Odronextamab's "
            "differentiation is its potential for fixed-duration treatment (step-up dosing with "
            "possible treatment-free remission) and subcutaneous formulation in development. "
            "The FL BLA is the lead indication — approval would open the door for additional "
            "lymphoma subtypes."
        ),
    },

    # ── October 2026 ──
    {
        "ticker": "MRNA",
        "title": "Phase 3 readout — mRNA-4157 (personalized cancer vaccine)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 10, 5, 0, 0),
        "impact_level": "High",
        "drug_name": "mRNA-4157 (V940)",
        "mechanism": "Personalized neoantigen mRNA cancer vaccine encoding up to 34 patient-specific mutations",
        "trial_phase": "Phase 3",
        "trial_name": "KEYNOTE-942 / V940-001 (adjuvant melanoma)",
        "milestone": "Primary RFS analysis in high-risk resected melanoma",
        "background": (
            "mRNA-4157 (now V940) is the first mRNA personalized cancer vaccine to enter Phase 3. "
            "It encodes up to 34 patient-specific tumor mutations identified by sequencing, training "
            "the immune system to recognize and attack residual cancer cells. In Phase 2b "
            "(KEYNOTE-942), the combination with Keytruda showed a 44% reduction in recurrence "
            "or death versus Keytruda alone in resected high-risk melanoma. The Phase 3 is "
            "expanding into other tumor types. This is Moderna's most important pipeline catalyst "
            "outside infectious disease and could validate the entire personalized cancer vaccine "
            "field."
        ),
    },
    {
        "ticker": "BMRN",
        "title": "PDUFA date — vosoritide (achondroplasia, under 5)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 10, 8, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Vosoritide (BMN-111, Voxzogo)",
        "mechanism": "C-type natriuretic peptide (CNP) analog — promotes endochondral bone growth",
        "trial_phase": "Phase 3 (pediatric expansion)",
        "trial_name": "Early-Start Study (ages 0–5)",
        "milestone": "FDA decision on label expansion to children under 5",
        "background": (
            "Vosoritide is already approved for achondroplasia (most common form of dwarfism) in "
            "children aged 5+. This sNDA extends the indication to infants and toddlers under 5, "
            "where early intervention could produce even better growth outcomes. The early-start "
            "data show normalization of growth velocity toward non-achondroplastic percentiles. "
            "Expanding the label younger captures patients earlier and increases lifetime treatment "
            "duration — a significant commercial opportunity."
        ),
    },
    {
        "ticker": "SNY",
        "title": "Phase 3 readout — tolebrutinib (multiple sclerosis)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 10, 12, 0, 0),
        "impact_level": "High",
        "drug_name": "Tolebrutinib (SAR442168)",
        "mechanism": "Brain-penetrant BTK inhibitor — targets B cells and microglia in CNS",
        "trial_phase": "Phase 3",
        "trial_name": "GEMINI 1 & 2 (relapsing MS), PERSEUS (primary progressive MS)",
        "milestone": "Pooled analysis of relapse rate and disability progression",
        "background": (
            "Tolebrutinib is Sanofi's BTK inhibitor designed to cross the blood-brain barrier, "
            "targeting both peripheral B cells and CNS-resident microglia — addressing the "
            "compartmentalized inflammation that drives progressive MS. The BTK inhibitor class "
            "is one of the most competitive in MS with Merck (evobrutinib), Roche (fenebrutinib), "
            "and Novartis (remibrutinib) all pursuing similar programs. Tolebrutinib's brain "
            "penetration is the key differentiator. Positive Phase 3 data would make tolebrutinib "
            "a potential first-line oral therapy for all forms of MS."
        ),
    },
    {
        "ticker": "EXEL",
        "title": "Phase 3 readout — zanzalintinib (colorectal cancer)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 10, 18, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Zanzalintinib (XL-092)",
        "mechanism": "Multi-kinase inhibitor (VEGFR, MET, TAM kinases) + immunotherapy combination",
        "trial_phase": "Phase 3",
        "trial_name": "EXPLORER (refractory CRC with atezolizumab)",
        "milestone": "Progression-free survival and overall survival data",
        "background": (
            "Zanzalintinib is Exelixis' next-generation tyrosine kinase inhibitor targeting VEGFR, "
            "MET, and TAM kinases with improved pharmacokinetics over cabozantinib. The EXPLORER "
            "trial combines zanzalintinib with atezolizumab (Tecentriq) in chemotherapy-refractory "
            "colorectal cancer — a setting with very limited options. Exelixis is positioning "
            "zanzalintinib as a potential cabozantinib replacement with better tolerability and "
            "broader combinability with immunotherapies."
        ),
    },
    {
        "ticker": "NTLA",
        "title": "Phase 1 readout — NTLA-2002 (hereditary angioedema)",
        "event_type": "PHASE1_READOUT",
        "event_date": datetime.datetime(2026, 10, 20, 0, 0),
        "impact_level": "Low",
        "drug_name": "NTLA-2002",
        "mechanism": "In vivo CRISPR gene editing — knocks out KLKB1 to reduce prekallikrein production",
        "trial_phase": "Phase 1/2",
        "trial_name": "NTLA-2002-001",
        "milestone": "Initial proof-of-concept data in HAE patients",
        "background": (
            "NTLA-2002 is Intellia's second in vivo CRISPR candidate, targeting KLKB1 (kallikrein B1) "
            "to reduce prekallikrein levels as a one-time treatment for hereditary angioedema (HAE). "
            "Following the success of NTLA-2001 (transthyretin amyloidosis), this program represents "
            "the expansion of in vivo CRISPR into a new disease area. Current HAE treatments are "
            "lifelong prophylactics or on-demand therapies. A one-time gene editing cure would be "
            "transformative. This early readout focuses on safety and proof-of-mechanism (kallikrein "
            "reduction levels)."
        ),
    },
    {
        "ticker": "FATE",
        "title": "Phase 2 update — FT-819 (systemic lupus erythematosus)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 10, 25, 0, 0),
        "impact_level": "Medium",
        "drug_name": "FT-819",
        "mechanism": "Off-the-shelf (allogeneic) CD19 CAR-T from iPSC-derived T cells",
        "trial_phase": "Phase 1/2",
        "trial_name": "Lupus nephritis and non-renal SLE cohort",
        "milestone": "Efficacy update in autoimmune lupus",
        "background": (
            "FT-819 is Fate's iPSC-derived allogeneic CD19 CAR-T therapy, initially developed for "
            "B-cell malignancies and now being explored in autoimmune disease following the "
            "breakthrough results from autologous CAR-T in lupus at Erlangen. As an off-the-shelf "
            "product, FT-819 could solve the manufacturing bottleneck of autologous CAR-T. "
            "Fate's iPSC platform allows unlimited doses from a single cell bank. This update "
            "will show early efficacy signals in lupus nephritis and potentially expand into "
            "other autoimmune indications."
        ),
    },
    {
        "ticker": "AZN",
        "title": "PDUFA date — capivasertib (HR+/HER2- breast cancer)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 10, 28, 0, 0),
        "impact_level": "High",
        "drug_name": "Capivasertib (AZD5363)",
        "mechanism": "Pan-AKT inhibitor — blocks PI3K/AKT/mTOR pathway",
        "trial_phase": "Phase 3",
        "trial_name": "CAPItello-291 (HR+/HER2- breast cancer with AKT pathway alterations)",
        "milestone": "FDA decision on NDA for AKT-mutant breast cancer",
        "background": (
            "Capivasertib is AstraZeneca's pan-AKT inhibitor for HR+/HER2- breast cancer with "
            "PIKCA/AKT/PTEN alterations. In the CAPItello-291 trial, it showed significant PFS "
            "benefit when combined with fulvestrant versus fulvestrant alone, specifically in "
            "the AKT-altered subgroup. This addresses a critical unmet need because patients with "
            "AKT pathway alterations have worse prognosis and these mutations are not targeted by "
            "currently approved therapies. Approval would make capivasertib the first AKT "
            "inhibitor approved in breast cancer."
        ),
    },

    # ── November 2026 ──
    {
        "ticker": "AMGN",
        "title": "Phase 2 readout — AMG 193 (MTAP-null solid tumors)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 11, 5, 0, 0),
        "impact_level": "Medium",
        "drug_name": "AMG 193",
        "mechanism": "PRMT5 inhibitor — synthetic lethality in MTAP-deleted tumors",
        "trial_phase": "Phase 2",
        "trial_name": "MTAP-null solid tumor basket study",
        "milestone": "Response rate across tumor types in biomarker-selected patients",
        "background": (
            "AMG 193 targets PRMT5, a synthetic lethal vulnerability in tumors with homozygous "
            "MTAP deletion — present in ~15% of all cancers (including pancreatic, NSCLC, and "
            "mesothelioma). The MTAP deletion creates a dependency on PRMT5 that normal cells "
            "don't share. This is Amgen's lead precision oncology program and a key test of "
            "the synthetic lethality paradigm outside of PARP inhibitors. Early data showed "
            "encouraging responses in heavily pre-treated patients."
        ),
    },
    {
        "ticker": "IONS",
        "title": "Phase 3 readout — olezarsen (familial chylomicronemia syndrome)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 11, 7, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Olezarsen (IONIS-APOC3-LRx)",
        "mechanism": "Antisense oligonucleotide targeting APOC3 mRNA to reduce triglycerides",
        "trial_phase": "Phase 3",
        "trial_name": "BALANCE (FCS), CORE (severe hypertriglyceridemia)",
        "milestone": "Triglyceride reduction and pancreatitis event data",
        "background": (
            "Olezarsen is Ionis' antisense therapy targeting APOC3 for familial chylomicronemia "
            "syndrome (FCS), a rare genetic disorder causing extremely high triglycerides and "
            "life-threatening pancreatitis. The drug reduces APOC3 protein production, enabling "
            "lipoprotein lipase-mediated clearance of triglyceride-rich particles. Phase 2 data "
            "showed ~77% triglyceride reduction. Ionis recently partnered with Novartis on "
            "olezarsen (and next-gen pelacarsen), validating the program. Approval would be "
            "the first disease-modifying therapy for FCS."
        ),
    },
    {
        "ticker": "DNLI",
        "title": "Phase 1/2 update — DNL-310 (Hunter syndrome)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 11, 12, 0, 0),
        "impact_level": "Medium",
        "drug_name": "DNL-310 (tividenofusp alfa)",
        "mechanism": "BBB-penetrant IDS enzyme replacement therapy using Denali's TV transport system",
        "trial_phase": "Phase 1/2",
        "trial_name": "Hunter syndrome (MPS II) dose-ranging study",
        "milestone": "Urine GAG reduction and neurocognitive outcomes",
        "background": (
            "DNL-310 is Denali's IDS enzyme replacement therapy engineered with their "
            "Transcending-Vehicle (TV) technology to cross the blood-brain barrier. Hunter "
            "syndrome (MPS II) is a lysosomal storage disease where current ERT (Elaprase) "
            "doesn't reach the brain, leaving CNS manifestations untreated. DNL-310 showed "
            "normalization of CSF GAG levels (the brain biomarker) in Phase 1/2, suggesting "
            "brain penetrance. This update will show longer-term neurocognitive outcomes — "
            "the key efficacy measure for regulatory approval."
        ),
    },
    {
        "ticker": "CRSP",
        "title": "Regulatory update — CASGEVY label expansion (TDT)",
        "event_type": "REGULATORY",
        "event_date": datetime.datetime(2026, 11, 15, 0, 0),
        "impact_level": "Medium",
        "drug_name": "CASGEVY (exagamglogene autotemcel, exa-cel)",
        "mechanism": "CRISPR/Cas9-edited CD34+ cells — BCL11A enhancer knockout to reactivate HbF",
        "trial_phase": "Approved (label expansion)",
        "trial_name": "CLIMB-111 (SCD), CLIMB-211 (TDT)",
        "milestone": "European CHMP opinion / FDA label expansion to TDT (transfusion-dependent beta-thalassemia)",
        "background": (
            "CASGEVY is the first CRISPR-based therapy approved anywhere in the world, originally "
            "for sickle cell disease. This regulatory event covers the label expansion to "
            "transfusion-dependent beta-thalassemia (TDT). In CLIMB-211, 91.7% of TDT patients "
            "became transfusion-free. Label expansion opens a similar-sized patient population "
            "and validates the platform economics. CRISPR Therapeutics and Vertex share profits "
            "50/50, so every indication expansion directly benefits CRSP."
        ),
    },
    {
        "ticker": "MRNA",
        "title": "Phase 2 readout — mRNA-1893 (cytomegalovirus vaccine)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 11, 18, 0, 0),
        "impact_level": "Low",
        "drug_name": "mRNA-1893",
        "mechanism": "mRNA vaccine encoding CMV glycoprotein B and pentamer complex",
        "trial_phase": "Phase 2",
        "trial_name": "CMV vaccine dose-confirmation study",
        "milestone": "Immunogenicity and safety update in healthy adults",
        "background": (
            "mRNA-1893 is Moderna's vaccine candidate for cytomegalovirus (CMV), the most common "
            "congenital infection worldwide and a major cause of hearing loss and developmental "
            "disability in newborns. No CMV vaccine is currently approved. Moderna's mRNA platform "
            "encodes two CMV antigens (gB and pentamer) designed to generate both neutralizing "
            "antibodies and T-cell responses. The Phase 2 data will inform dose selection for "
            "the pivotal Phase 3 trial. A successful CMV vaccine would address a major unmet "
            "medical need with significant public health impact."
        ),
    },
    {
        "ticker": "RCKT",
        "title": "Phase 2 readout — RP-A501 (Danon disease)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 11, 20, 0, 0),
        "impact_level": "Low",
        "drug_name": "RP-A501 (LAMP2 gene therapy)",
        "mechanism": "AAV9-mediated LAMP2B gene replacement for Danon cardiomyopathy",
        "trial_phase": "Phase 2",
        "trial_name": "Danon disease pivotal study",
        "milestone": "Cardiac functional and structural outcomes",
        "background": (
            "RP-A501 is Rocket Pharmaceuticals' AAV-based gene therapy for Danon disease, a rare "
            "X-linked genetic disorder causing severe cardiomyopathy, skeletal myopathy, and "
            "cognitive impairment. The disease is caused by LAMP2 mutations leading to "
            "autophagic buildup in cardiac muscle. RP-A501 delivers a functional LAMP2B gene. "
            "Rocket has received Breakthrough Therapy and Rare Pediatric Disease designations. "
            "Positive Phase 2 data would be the first disease-modifying therapy for Danon "
            "disease and support accelerated approval."
        ),
    },
    {
        "ticker": "BGNE",
        "title": "Phase 3 readout — sonrotoclax (CLL)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 11, 25, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Sonrotoclax (BGB-11417)",
        "mechanism": "Next-generation selective BCL2 inhibitor",
        "trial_phase": "Phase 3",
        "trial_name": "CELESTIAL (first-line CLL)",
        "milestone": "PFS data versus standard-of-care in treatment-naive CLL",
        "background": (
            "Sonrotoclax is BeiGene's next-generation BCL2 inhibitor designed to be more selective "
            "and potentially safer than venetoclax (AbbVie/Roche). As a more selective BCL2 "
            "inhibitor, it may avoid the tumor lysis syndrome and myelosuppression that limit "
            "venetoclax. BeiGene is also combining sonrotoclax with their BTK inhibitor "
            "zanubrutinib (Brukinsa) for a potential all-oral, chemotherapy-free CLL regimen. "
            "This is BeiGene's most important pipeline asset following zanubrutinib's success."
        ),
    },
    {
        "ticker": "KURA",
        "title": "PDUFA date — ziftomenib (NPM1-mutant AML)",
        "event_type": "PDUFA",
        "event_date": datetime.datetime(2026, 11, 30, 0, 0),
        "impact_level": "High",
        "drug_name": "Ziftomenib (KO-539)",
        "mechanism": "Menin inhibitor — blocks menin-KMT2A interaction in NPM1-mutant AML",
        "trial_phase": "Phase 2 (pivotal)",
        "trial_name": "KOMET-001 (NPM1-mutant relapsed/refractory AML)",
        "milestone": "FDA decision on accelerated approval based on CR rate",
        "background": (
            "Ziftomenib is Kura Oncology's menin inhibitor targeting NPM1-mutant acute myeloid "
            "leukemia — a genetically defined subset of ~30% of AML patients. The menin-MLL "
            "interaction is a validated target in NPM1-mutant and KMT2A-rearranged leukemias. "
            "In Phase 1/2, ziftomenib showed a 35% complete response rate in heavily "
            "pre-treated NPM1-mutant AML with a favorable safety profile (low differentiation "
            "syndrome versus competitors). The PDUFA decision could make ziftomenib the first "
            "approved menin inhibitor and the first targeted therapy for NPM1-mutant AML."
        ),
    },

    # ── December 2026 ──
    {
        "ticker": "EDIT",
        "title": "Phase 1/2 update — EDIT-301 (sickle cell disease)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 12, 1, 0, 0),
        "impact_level": "Medium",
        "drug_name": "EDIT-301 (reni-cel)",
        "mechanism": "CRISPR/Cas12a editing at HBG promoter to reactivate fetal hemoglobin (HbF)",
        "trial_phase": "Phase 1/2",
        "trial_name": "RUBY trial (SCD), EdiThal trial (TDT)",
        "milestone": "Updated durability and fetal hemoglobin data",
        "background": (
            "EDIT-301 is Editas' CRISPR/Cas12a-edited cell therapy for sickle cell disease and "
            "beta-thalassemia. Unlike CASGEVY which uses Cas9, EDIT-301 uses Cas12a, which "
            "Editas claims enables more precise editing and better engraftment. The therapy "
            "edits the HBG promoter to boost fetal hemoglobin. Early data showed all treated "
            "patients achieving normal hemoglobin levels with no vaso-occlusive events. This "
            "update will show durability beyond 12 months and potentially the first TDT patient data."
        ),
    },
    {
        "ticker": "RXRX",
        "title": "Phase 2 readout — REC-2282 (neurofibromatosis type 2)",
        "event_type": "PHASE2_READOUT",
        "event_date": datetime.datetime(2026, 12, 5, 0, 0),
        "impact_level": "Low",
        "drug_name": "REC-2282",
        "mechanism": "HDAC inhibitor discovered via Recursion's AI platform — penetrates BBB",
        "trial_phase": "Phase 2",
        "trial_name": "NF2-related schwannomatosis (phase 2/3)",
        "milestone": "Tumor response rate in patients with NF2 mutations",
        "background": (
            "REC-2282 is Recursion's AI-discovered HDAC inhibitor for neurofibromatosis type 2 "
            "(NF2), a genetic condition causing benign tumors on cranial and spinal nerves. "
            "The drug was identified through Recursion's phenotypic screening platform. "
            "This is a key validation point for Recursion's AI-driven drug discovery approach: "
            "can an AI-discovered drug show clinical efficacy? REC-2282 has Orphan Drug and "
            "Rare Pediatric Disease designations. Even modest tumor shrinkage would be "
            "meaningful for patients who currently have no approved therapies."
        ),
    },
    {
        "ticker": "VERV",
        "title": "Phase 1b readout — VERVE-101 (heterozygous FH)",
        "event_type": "PHASE1_READOUT",
        "event_date": datetime.datetime(2026, 12, 10, 0, 0),
        "impact_level": "Medium",
        "drug_name": "VERVE-101",
        "mechanism": "In vivo base editing — permanently edits PCSK9 gene in liver to lower LDL-C",
        "trial_phase": "Phase 1b",
        "trial_name": "heart-1 (heterozygous familial hypercholesterolemia)",
        "milestone": "LDL-C reduction durability beyond 12 months",
        "background": (
            "VERVE-101 is the first in vivo base editing therapy ever tested in humans, designed "
            "to permanently inactivate the PCSK9 gene in liver cells via a single infusion of "
            "lipid nanoparticles containing base editing machinery. The goal is one-shot "
            "permanent LDL cholesterol reduction — potentially eliminating the need for daily "
            "statin or PCSK9 inhibitor injections. Phase 1a showed proof-of-mechanism with "
            "sustained LDL-C reduction. Phase 1b will test dose optimization and show durability "
            "data. This is a landmark program for the entire in vivo genome editing field."
        ),
    },
    {
        "ticker": "ALLO",
        "title": "Phase 1 update — ALLO-501A (lupus nephritis)",
        "event_type": "PHASE1_READOUT",
        "event_date": datetime.datetime(2026, 12, 15, 0, 0),
        "impact_level": "Low",
        "drug_name": "ALLO-501A",
        "mechanism": "Allogeneic anti-CD19 CAR-T cells with Cellectis TALEN gene editing",
        "trial_phase": "Phase 1",
        "trial_name": "ALLO-501A in autoimmune lupus"
                   "",
        "milestone": "Safety and early efficacy signals in lupus nephritis",
        "background": (
            "ALLO-501A is Allogene's allogeneic CAR-T therapy targeting CD19 for autoimmune "
            "disease, following the remarkable success of autologous CAR-T in SLE. Using "
            "TALEN-edited donor T cells, ALLO-501A could provide an off-the-shelf alternative "
            "to individualized CAR-T manufacturing. This will be one of the earliest allogeneic "
            "CAR-T datasets in autoimmune disease. After significant challenges with allogeneic "
            "CAR-T in oncology (persistence issues), the autoimmune setting where transient "
            "B-cell depletion may suffice could be the ideal application."
        ),
    },
    {
        "ticker": "UTHR",
        "title": "Phase 3 readout — ralinepag (pulmonary arterial hypertension)",
        "event_type": "PHASE3_READOUT",
        "event_date": datetime.datetime(2026, 12, 20, 0, 0),
        "impact_level": "Medium",
        "drug_name": "Ralinepag (APD811)",
        "mechanism": "Oral IP prostacyclin receptor agonist — vasodilator for pulmonary arteries",
        "trial_phase": "Phase 3",
        "trial_name": "ADVANCE OUTCOMES (pivotal PAH study)",
        "milestone": "Composite morbidity/mortality event data",
        "background": (
            "Ralinepag is United Therapeutics' oral prostacyclin receptor agonist for pulmonary "
            "arterial hypertension (PAH), a rare progressive disease. Current prostacyclin "
            "therapies require continuous IV/subcutaneous infusion (Flolan, Remodulin) or "
            "inhaled (Ventavis). An oral option with once-daily dosing and better tolerability "
            "could capture significant market share from the injectables. ADVANCE OUTCOMES is "
            "an event-driven trial measuring time to clinical worsening. Positive data would "
            "make ralinepag the third oral prostacyclin after selexipag (Uptravi) and oral "
            "treprostinil (Orenitram)."
        ),
    },
]


def seed_database(db: Session) -> int:
    """Insert seed data. Returns number of tickers added."""
    count = 0
    for t in SEED_TICKERS:
        existing = db.query(Ticker).filter(Ticker.ticker == t["ticker"]).first()
        if not existing:
            db.add(Ticker(**t))
            count += 1

    db.flush()  # ensure tickers have IDs before inserting events

    # Map ticker → ID
    ticker_map = {t.ticker: t.id for t in db.query(Ticker).all()}

    for ev in SEED_EVENTS:
        # Build a rich background summary from the structured fields
        summary_parts = []
        summary_parts.append(f"💊 Drug: {ev.get('drug_name', ev['title'])}")
        summary_parts.append(f"⚙️  Mechanism: {ev.get('mechanism', 'N/A')}")
        summary_parts.append(f"🔬 Phase: {ev.get('trial_phase', ev['event_type'])}")
        summary_parts.append(f"📋 Trial: {ev.get('trial_name', 'N/A')}")
        summary_parts.append(f"🎯 Milestone: {ev.get('milestone', ev['title'])}")
        summary_parts.append("")
        summary_parts.append(ev.get("background", ""))
        full_description = "\n".join(summary_parts)

        existing = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.ticker == ev["ticker"],
                CatalystEvent.title == ev["title"],
            )
            .first()
        )
        if not existing:
            db.add(
                CatalystEvent(
                    ticker_id=ticker_map.get(ev["ticker"], 0),
                    ticker=ev["ticker"],
                    title=ev["title"],
                    event_type=ev["event_type"],
                    event_date=ev["event_date"],
                    impact_level=ev["impact_level"],
                    description=full_description,
                )
            )

    db.commit()
    return count
