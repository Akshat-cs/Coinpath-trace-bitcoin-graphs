# Coinpath Graph Trace (Bitcoin) — Video Tutorial Script (~2 min)

---

## [0:00–0:10] Hook

"Want to trace where Bitcoin went — in one command? In this video, I'll show you how to use Bitquery's Coinpath API to generate interactive investigation graphs for Bitcoin, straight from your terminal."

---

## [0:10–0:30] What is Coinpath?

"Coinpath is Bitquery's fund-tracing API. You give it a Bitcoin address, and it traces the money — both inbound and outbound — across multiple hops.

It works on Bitcoin, Litecoin, Dogecoin, Dash, Bitcoin Cash, and other UTXO chains.

This repo wraps that API into a single CLI tool that generates two outputs: an interactive HTML graph for quick exploration, and a GEXF file for deep analysis in Gephi."

---

## [0:30–0:55] Setup (screen recording)

"Let's set it up. Clone the repo, install two Python dependencies, and drop your Bitquery API token into the env file."

*Show terminal:*
```
git clone https://github.com/bitquery/coinpath-graph-trace.git
cd coinpath-graph-trace
pip install -r requirements.txt
cp .env.example .env
```

"Paste your Bitquery OAuth token here — you can get this from your Bitquery account dashboard."

*Show pasting token into .env*

---

## [0:55–1:20] Run the trace (screen recording)

"Now let's trace a Bitcoin address. I'll trace this address for transactions from October 2023 to January 2024."

*Show terminal:*
```
python3 coinpath_trace.py bc1p4kufll9uhnpkgzuc65slcxd2qaw2hl9xecket3h8yyu4awglcsqslqaztd \
  --network bitcoin --from 2023-10-10 --till 2024-01-01
```

"It hits the Coinpath API — first fetching outbound flows, then inbound — and generates three files: the raw JSON, a Gephi graph file, and an interactive HTML visualization."

*Show the output:*
```
Fetching outbound flows...
Fetching inbound flows...
Received 10 outbound + 10 inbound transfers
Graph: 17 nodes, 20 edges
```

---

## [1:20–1:50] Explore the graph (screen recording)

"Let me open the HTML file."

*Open in browser, show the graph*

"Nodes are color-coded:
- Red is the source address we traced
- Blue nodes are relays — they receive and forward BTC
- Green nodes are sinks — dead ends where Bitcoin stopped moving

Hover over any node to see its full address, role, and total in/out volume in BTC and USD.

You can drag nodes to rearrange the layout. And if you click a node, it copies the full Bitcoin address to your clipboard — handy for looking it up on a block explorer.

Edge brightness tells you the depth — brighter orange means a direct transfer, fainter means further hops."

---

## [1:50–2:00] Closing + CTA

"You can also open the GEXF file in Gephi for advanced analysis — force-directed layouts, clustering, centrality metrics — all the data is baked in.

It works on Bitcoin, Litecoin, Dogecoin, and other UTXO chains. Check the link in the description, give it a star, and start tracing."

---

*END*
