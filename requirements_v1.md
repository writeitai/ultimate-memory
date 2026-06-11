# Requirements

## Ingestion
- all inputs are tracked in Postgres
- the entire system (vector + graph datbase layers) should be rebuildable based on the data that Postgres holds

### L0 - Files
- input files are stored on GCS
- they are transformed into Markdown files and saved in dedicated directory
- then they are processed via https://github.com/VectifyAI/PageIndex - we get a hierarchy + summaries for each document
- we should have ability to track files cross-references in DB (e.g. papers citing other papers)

### L1 - Chunks
- we use semchunk for chunking of the documents
- use Lance DB as the vector database
- make sure the indexes are properly designed and built
- the chunks must hold reference to the original input document

### L2 - Claims
- use the Claimify principle
- try to avoid decontextualization
- the extracted claims will be embedded and available via Lance DB

### L3 - General Knowledge
- the progressive disclosure summarization layer over the high-information claims

### L4 - Special-Purpose Knowledge Layers
- e.g. people profiles, business planning, paper idea concepts etc. - whatever the system is aimed or wants to be better at
- also git-tracked


## Deployment
- Postgres on Hetzner


## Processing
- via Cloud Run workers triggered via Cloud Tasks
- Cloud Tasks must have max. 2 retries
- Cloud Tasks must be rate-limited to a reasonable number

- each layer should have its own worker
- after the worker from one layer finishes, the next-level worker should be triggered

- the L3 and L4 should use Codex / OpenCode for processing
- we must make sure they always pull the latest main before they start and that they see the entire repo
- L3 and L4 must be a single repo 
  - the directories structure must distinctly split the two
  - the L4 can have multiple special-purpose memory layers/directories
- they should be able to handle merge conflicts - i.e. they must re-try with the same session
- some highly-frequent edited files like root-level index.md might have to be edited by a separate worker that would be triggered after a rolling-window delay
  - i.e. if it gets a signal, there will be some delay before it starts
  - if the signal is received again within the delay window, the delay gets restarted to original value
