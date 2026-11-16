# Military AI Research Agent

Research AI adoption and use in militaries worldwide through a cited Streamlit chatbot and a weekly academic digest. Topics include intelligence, decision support, logistics, maintenance, training, autonomy, human oversight, governance, ethics, and strategic effects.

## Updating the existing deployment

1. Copy `app.py`, `chat.py`, `main.py`, `foundational_pull.py`, and the new `research_focus.py` into the repository. Update both workflows in `.github/workflows/`.
2. Deploy the updated branch through your existing Streamlit app with `app.py` as the entry point. GitHub scheduled jobs use the default branch, so put the workflow and its Python files there to update the weekly digest.
3. Keep the existing OpenAI, Supabase, and Gmail environment settings. The code uses the existing Supabase `chunks` table and embedding model. Existing IR papers provide background context.
4. Run the **Foundational Military AI Paper Pull** workflow manually to seed the library with up to 50 highly cited relevant papers from 2010 onward. This calls OpenAI and writes to Supabase.
5. Ask the chatbot about military AI and inspect its cited passages. The **Run Military AI Research Agent** workflow adds recent research and sends the weekly digest. Manually running this workflow also sends an email.

The discovery terms and shared answer instructions live in `research_focus.py`. Candidate papers must mention both AI or autonomy and a military context in their title or abstract. This heuristic can miss relevant research or admit incidental mentions. The weekly search starts in 2024, considers up to 30 ranked candidates, and processes up to 10. The foundational search takes the 50 most cited relevant results from its topic searches. Geographic coverage depends on the available literature.

Answers use the Supabase library and distinguish deployment evidence from trials, announcements, and speculation. Academic sources and manually uploaded PDFs determine freshness and coverage. Earlier IR literature remains accessible. Date filters now default to the full supported range, and chat retrieval reads all result pages to include newly added papers.

The existing JSON field names are retained for database compatibility. In new digests, `strategic_infrastructure_relevance` describes military AI applications and adoption, and `ir_scholars_relevance` describes implications for security scholarship.

To check connections, run **Run Military AI Research Agent** manually with **check_connections_only** selected. It tests a Supabase read, an OpenAlex search, and Gmail SMTP login. This mode sends no email and writes no research data. An optional GitHub Actions secret named `OPENALEX_API_KEY` increases the OpenAlex request budget. The weekly collector uses basic pagination with up to six pages of 100 results per search.

Local validation covers Python syntax, topic selection, foundational discovery with mocked results, and paginated retrieval. Live OpenAI, Supabase, Gmail, and Streamlit verification requires the deployed environment.
