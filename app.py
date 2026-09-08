import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import streamlit as st

OPENALEX_API = "https://api.openalex.org"
REQUEST_TIMEOUT = 20
USER_AGENT = "doi-author-explorer/1.0"

st.set_page_config(
    page_title="DOI Author Explorer",
    page_icon="📚",
    layout="wide",
)


def normalize_doi(raw: str) -> str:
    doi = raw.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def is_valid_doi(doi: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.IGNORECASE))


def get_json(url: str, params=None):
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60 * 60)
def fetch_work_by_doi(doi: str):
    # OpenAlex supports DOI lookup by external DOI identifier.
    doi_url = f"https://doi.org/{doi}"
    url = f"{OPENALEX_API}/works/{doi_url}"
    return get_json(url)


@st.cache_data(ttl=60 * 60)
def fetch_author(author_id: str):
    short_id = author_id.rstrip("/").split("/")[-1]
    return get_json(f"{OPENALEX_API}/authors/{short_id}")


def format_orcid(orcid_value):
    if not orcid_value:
        return ""
    return str(orcid_value).replace("https://orcid.org/", "")


def primary_institution(author_record):
    affiliations = author_record.get("affiliations") or []
    if affiliations:
        inst = affiliations[0].get("institution") or {}
        return inst.get("display_name") or ""

    last_known = author_record.get("last_known_institutions") or []
    if last_known:
        return last_known[0].get("display_name") or ""

    return ""


def build_author_table(work):
    authorships = work.get("authorships") or []
    author_refs = []
    seen = set()

    for authorship in authorships:
        author = authorship.get("author") or {}
        author_id = author.get("id")
        if not author_id or author_id in seen:
            continue
        seen.add(author_id)
        author_refs.append(
            {
                "author_id": author_id,
                "fallback_name": author.get("display_name") or "Unknown author",
                "position": authorship.get("author_position") or "",
                "is_corresponding": bool(authorship.get("is_corresponding")),
            }
        )

    rows = []
    errors = []

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(author_refs)))) as executor:
        future_map = {
            executor.submit(fetch_author, item["author_id"]): item for item in author_refs
        }

        for future in as_completed(future_map):
            item = future_map[future]
            try:
                author = future.result()
                rows.append(
                    {
                        "Author": author.get("display_name") or item["fallback_name"],
                        "Publications": author.get("works_count", 0),
                        "Citations": author.get("cited_by_count", 0),
                        "h-index": (author.get("summary_stats") or {}).get("h_index", ""),
                        "ORCID": format_orcid(author.get("orcid")),
                        "Institution": primary_institution(author),
                        "Author position": item["position"].title(),
                        "Corresponding": "Yes" if item["is_corresponding"] else "",
                        "OpenAlex ID": author.get("id") or item["author_id"],
                    }
                )
            except Exception as exc:
                errors.append(f"{item['fallback_name']}: {exc}")
                rows.append(
                    {
                        "Author": item["fallback_name"],
                        "Publications": "",
                        "Citations": "",
                        "h-index": "",
                        "ORCID": "",
                        "Institution": "",
                        "Author position": item["position"].title(),
                        "Corresponding": "Yes" if item["is_corresponding"] else "",
                        "OpenAlex ID": item["author_id"],
                    }
                )

    # Keep original paper-author order where possible.
    order = {item["author_id"]: i for i, item in enumerate(author_refs)}
    rows.sort(key=lambda r: order.get(r["OpenAlex ID"], 9999))

    return pd.DataFrame(rows), errors


st.title("📚 DOI Author Explorer")
st.write(
    "Enter a DOI to see the paper's authors alongside their publication counts and selected author metrics from OpenAlex."
)

with st.form("doi_form"):
    doi_input = st.text_input(
        "DOI",
        placeholder="e.g. 10.1038/s41586-024-07386-0",
        help="You can paste either a DOI or a full https://doi.org/... link.",
    )
    submitted = st.form_submit_button("Search")

if submitted:
    doi = normalize_doi(doi_input)

    if not doi:
        st.warning("Please enter a DOI.")
    elif not is_valid_doi(doi):
        st.warning("That does not look like a valid DOI. Please check it and try again.")
    else:
        try:
            with st.spinner("Looking up the paper and author records..."):
                work = fetch_work_by_doi(doi)
                df, author_errors = build_author_table(work)

            title = work.get("title") or "Untitled work"
            publication_year = work.get("publication_year") or ""
            venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""

            st.subheader(title)
            meta_parts = [part for part in [str(publication_year) if publication_year else "", venue] if part]
            if meta_parts:
                st.caption(" • ".join(meta_parts))

            col1, col2, col3 = st.columns(3)
            col1.metric("Authors", len(df))
            if not df.empty and pd.api.types.is_numeric_dtype(df["Publications"]):
                col2.metric("Combined publication count", f"{int(df['Publications'].sum()):,}")
                col3.metric("Median publications", f"{int(df['Publications'].median()):,}")
            else:
                col2.metric("Combined publication count", "—")
                col3.metric("Median publications", "—")

            display_cols = [
                "Author",
                "Publications",
                "Citations",
                "h-index",
                "ORCID",
                "Institution",
                "Author position",
                "Corresponding",
                "OpenAlex ID",
            ]

            st.dataframe(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Publications": st.column_config.NumberColumn(format="%d"),
                    "Citations": st.column_config.NumberColumn(format="%d"),
                    "h-index": st.column_config.NumberColumn(format="%d"),
                    "OpenAlex ID": st.column_config.LinkColumn("OpenAlex ID", display_text="OpenAlex profile"),
                },
            )

            csv = df.to_csv(index=False).encode("utf-8")
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", doi)
            st.download_button(
                "Download CSV",
                data=csv,
                file_name=f"doi_authors_{safe_name}.csv",
                mime="text/csv",
            )

            st.info(
                "Publication count is OpenAlex's total works_count for each author record. "
                "It can include more than journal articles, such as conference papers or other indexed works."
            )

            if author_errors:
                with st.expander("Some author records could not be fully loaded"):
                    for message in author_errors:
                        st.write(message)

        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 404:
                st.error("No OpenAlex work was found for that DOI.")
            else:
                st.error(f"The lookup failed with an HTTP error: {exc}")
        except requests.RequestException as exc:
            st.error(f"Could not reach OpenAlex: {exc}")
        except Exception as exc:
            st.error(f"Something went wrong: {exc}")

st.divider()
st.caption("Data source: OpenAlex. No database is required for this app.")
