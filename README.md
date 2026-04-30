# Coinpath Trace (Bitcoin)

Trace Bitcoin fund flows using [Bitquery's Coinpath API](https://docs.bitquery.io/v1/docs/Schema/bitcoin/coinpath) and generate interactive HTML graphs + [Gephi](https://gephi.org/)-compatible GEXF files — all from a single CLI command.

**Give it a Bitcoin address, get a graph.**

## What It Does

1. Queries Bitquery's Coinpath API (inbound + outbound fund flows)
2. Saves the raw JSON response
3. Generates a `.gexf` file you can open in Gephi for deep analysis
4. Generates a self-contained `.html` interactive graph you can open in any browser

## Supported Networks

Any UTXO chain supported by Bitquery's V1 API:

| Network      | `--network` value |
| ------------ | ----------------- |
| Bitcoin      | `bitcoin`         |
| Litecoin     | `litecoin`        |
| Bitcoin Cash | `bitcash`         |
| Bitcoin SV   | `bitcoinsv`       |
| Dogecoin     | `dogecoin`        |
| Dash         | `dash`            |
| Zcash        | `zcash`           |

## Setup

```bash
git clone https://github.com/bitquery/coinpath-graph-trace.git
cd coinpath-graph-trace
pip install -r requirements.txt
```

Copy the example env file and add your Bitquery OAuth token:

```bash
cp .env.example .env
# Edit .env and paste your token
```

Get your token from [Bitquery Account](https://account.bitquery.io/).

## Usage

Three flags are **required**: `--network`, `--from`, `--till`.

### Trace a Bitcoin address

```bash
python3 coinpath_trace.py bc1p4kufll9uhnpkgzuc65slcxd2qaw2hl9xecket3h8yyu4awglcsqslqaztd \
  --network bitcoin \
  --from 2023-10-10 \
  --till 2024-01-01
```

### One-liner: query + open in browser

```bash
python3 coinpath_trace.py bc1p4kufll9uhnpkgzuc65slcxd2qaw2hl9xecket3h8yyu4awglcsqslqaztd \
  --network bitcoin --from 2023-10-10 --till 2024-01-01 \
  && open trace_bc1p4kuf_aztd.html
```

### Trace with more results

```bash
python3 coinpath_trace.py bc1p4kufll9uhnpkgzuc65slcxd2qaw2hl9xecket3h8yyu4awglcsqslqaztd \
  --network bitcoin \
  --from 2023-10-10 \
  --till 2024-01-01 \
  --limit 50
```

### Regenerate graph from saved JSON (no API call)

```bash
python3 coinpath_trace.py bc1p4kufll9uhnpkgzuc65slcxd2qaw2hl9xecket3h8yyu4awglcsqslqaztd \
  --network bitcoin --from 2023-10-10 --till 2024-01-01 \
  --json-input trace_bc1p4kuf_aztd.json
```

## Required Flags

| Flag        | Description                                    |
| ----------- | ---------------------------------------------- |
| `--network` | Chain: `bitcoin`, `litecoin`, `dogecoin`, etc. |
| `--from`    | Start date (e.g. `2024-01-01`)                 |
| `--till`    | End date (e.g. `2024-12-31`)                   |

## Optional Flags

| Flag           | Default | Description                   |
| -------------- | ------- | ----------------------------- |
| `--depth`      | `3`     | Max hops to trace             |
| `--limit`      | `25`    | Max results per depth level   |
| `--output`     | auto    | Output filename prefix        |
| `--json-input` | —       | Skip API call, use local JSON |

## Output Files

| File                | What it is                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------- |
| `trace_<addr>.json` | Raw Coinpath API response                                                                       |
| `trace_<addr>.gexf` | Graph file — open in [Gephi](https://gephi.org/) or [Gephi Lite](https://gephi.org/gephi-lite/) |
| `trace_<addr>.html` | Interactive graph — open in any browser                                                         |

## HTML Graph Features

- **Dark theme** with color-coded nodes by role (source, relay, sink, origin)
- **Hover** any node to see address, role, and in/out volumes (BTC + USD)
- **Drag** nodes to rearrange the layout
- **Click** a node to copy its full address to clipboard
- **Zoom/pan** to explore large graphs
- **Edge opacity** indicates trace depth (brighter = closer to source)

## When to Use Gephi

The HTML graph is great for quick exploration. Use Gephi when you need:

- **Force-directed layouts** (ForceAtlas2) to auto-cluster related wallets
- **Graph metrics** — PageRank, Betweenness Centrality, Modularity
- **Filtering** — hide small transfers, isolate paths
- **Export** publication-quality images for reports

## How It Works

```
Bitcoin Address + Date Range
       │
       ▼
┌──────────────────┐
│  Bitquery V1 API │  Outbound query (initialAddress) +
│  (Coinpath)      │  Inbound query (receiver)
└──────┬───────────┘
       │ JSON response
       ▼
┌──────────────────┐
│  Build Graph     │  Deduplicate nodes, assign roles, sum volumes
└──────┬───────────┘
       │
       ├──▶ trace.json   (raw API data)
       ├──▶ trace.gexf   (Gephi graph with attributes + colors)
       └──▶ trace.html   (Sigma.js interactive visualization)
```

## License

MIT
