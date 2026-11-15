# Legal sources: the human confirmation checklist

**Due Nov 16, before the demo.** An agent may not confirm a legal source, so this is a person's
job: open each URL, check the section, the form name and the wording, then fill in
`confirmed_by` and `confirmed_on` on the entry in `corpus.py`.

Until an entry has a `confirmed_by`, the app reports it as `unverified` whatever the URL check
finds, and the caseworker sees that in the sources list. Nothing else in the app depends on it:
the deadline comes from the rule attached to the evidence policy, not from the confirmation.

How to confirm one entry (about 15 minutes for the four):

1. Open the URL below in a browser.
2. Find the locator (`section 9(1)`, `page 4`).
3. Read the excerpt in `corpus.py` against the document. It must be word for word, with the
   PDF's line breaks joined by single spaces. Fix it if it is not; never paraphrase it.
4. Set `confirmed_by="<your name>"` and `confirmed_on="2026-11-16"` on that entry.
5. Run `uv run python -m app.services.legal.verify` (see `verify.py`); a confirmed entry whose
   text still matches the published document comes back `unchanged`.

## The entries

| # | Entry id | What it is | URL | Locator | Confirmed? by whom |
|---|---|---|---|---|---|
| 1 | `ns-rta-statutory-conditions` | Residential Tenancies Act (Nova Scotia), statutory conditions | https://nslegislature.ca/sites/default/files/legc/statutes/residential%20tenancies.pdf | section 9(1), statutory condition 1 (Condition of Premises) | **no** |
| 2 | `ns-evidence-policy-42-deadline` | Evidence Policy #42, the 5-day submission deadline | https://www.novascotia.ca/sites/default/files/documents/1-1319/evidence-policy-42-residential-tenancies-en.pdf | page 1, Details | **no** |
| 3 | `ns-evidence-policy-42-formats` | Evidence Policy #42, accepted formats | same document, `#page=4` | page 4, Types of Evidence | **no** |
| 4 | `ns-form-j` | Application to Director (Form J) | https://beta.novascotia.ca/sites/default/files/documents/2-419/form-j-application-director-en.pdf | page 1, applicant and dispute details | **no** |

## What each excerpt says

Verbatim, as stored in `corpus.py` today. Check these against the documents.

**1. RTA, statutory condition 1.**

> The landlord shall keep the premises in a good state of repair and fit for habitation during the
> tenancy and shall comply with any statutory enactment or law respecting standards of health,
> safety or housing.

**2. Evidence Policy #42, deadline.**

> If applicants or respondents intend to introduce evidence, other than oral testimony, during
> their hearing to demonstrate or explain their case they must submit their evidence at least 5
> days before their hearing date.

**3. Evidence Policy #42, formats.**

> Digital documents must be in one of the following formats: Microsoft Office Word, Microsoft
> Office Excel or Adobe PDF

**4. Form J.** No excerpt yet: the published PDF is encrypted and its text could not be read
here, so the entry has `excerpt=""` and stays `unverified`. Whoever confirms it should copy the
form's title line and the labels of the fields this app drafts against (below) into the entry.

## Decisions a person should look at

- **Form J's field labels are ours, not the form's.** The keys come from the seeded demo case
  (`tenant_name`, `landlord_name`, `landlord_address`, `rental_address`, `tenancy_start`,
  `monthly_rent`, `remedy`) and the labels are plain-English versions. Confirm them against the
  form before the demo, because the gaps step now writes these fields onto a case that has none.
- **Policy #28 ("Hearings Procedures and Conduct") is not in the corpus.** The URL the seed data
  carries
  (`.../ans-residential-tenancies-policy-28-residential-tenancies-hearings-procedures-and-conduct.pdf`)
  now redirects to the policy index, and the current index lists five policies, none of them
  #28. The nearest current document is Policy #40, Format of Hearings. Rather than cite a
  document that no longer exists, WS4 leaves it out: the demo case's `src_04` row keeps its dead
  URL and stays `unverified`. Retiring or repointing that row belongs to whoever owns the seed
  data, not to WS4.
- **The app accepts JPG, PNG, HEIC, PDF and TXT; the policy names Word, Excel and PDF for
  documents.** The app's photo handling matches the policy's "photographs are acceptable", and
  its TXT-to-PDF copy matches "text messages must be submitted digitally or printed". The gap is
  Word and Excel: the app refuses them. That is a WS1 decision, noted here so it is not a
  surprise at the demo.
