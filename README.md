DOI Author Explorer

A small Streamlit website that accepts a DOI and returns a table of the paper's authors alongside their OpenAlex publication counts, citations, h-index, ORCID, institution, and author position.

Run locally

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py

Deploy free on Streamlit Community Cloud

Create a new GitHub repository.

Upload app.py and requirements.txt (and optionally this README).

Go to Streamlit Community Cloud and create a new app from that repository.

Select app.py as the entry point and deploy.

No secrets or database are required for the basic version.

What "Publications" means

The Publications column uses the OpenAlex author record's works_count. This is the total number of works OpenAlex associates with that author and is not limited to journal articles.

Notes on author identity

The app uses the author identifiers attached to the DOI's OpenAlex work record rather than searching by author name. This reduces, but does not completely eliminate, author-disambiguation errors.
