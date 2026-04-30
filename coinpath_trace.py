#!/usr/bin/env python3
"""
Coinpath Trace (Bitcoin) — Query Bitquery's Coinpath API and generate Gephi (GEXF) + interactive HTML graphs.

Usage:
    python coinpath_trace.py <address> --network <chain> --from <date> --till <date>

Examples:
    python coinpath_trace.py bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh --network bitcoin --from 2024-01-01 --till 2024-06-01
    python coinpath_trace.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa --network bitcoin --from 2023-01-01 --till 2023-12-31 --depth 2
"""

import argparse
import json
import math
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

import requests
from dotenv import load_dotenv

load_dotenv()

BITQUERY_V1_ENDPOINT = "https://graphql.bitquery.io"

COINPATH_OUTBOUND_QUERY = """
query (
  $network: BitcoinNetwork!,
  $address: String!,
  $limit: Int!,
  $from: ISO8601DateTime,
  $till: ISO8601DateTime
) {
  bitcoin(network: $network) {
    outbound: coinpath(
      initialAddress: {is: $address}
      options: {limit: $limit, desc: "block.height"}
      date: {after: $from, before: $till}
    ) {
      sender { address }
      receiver { address }
      amount
      amountUSD: amount(in: USD)
      transaction { hash }
      depth
      block { height timestamp { time } }
      currency { symbol }
    }
  }
}
"""

COINPATH_INBOUND_QUERY = """
query (
  $network: BitcoinNetwork!,
  $address: String!,
  $limit: Int!,
  $from: ISO8601DateTime,
  $till: ISO8601DateTime
) {
  bitcoin(network: $network) {
    inbound: coinpath(
      receiver: {is: $address}
      options: {limit: $limit, desc: "block.height"}
      date: {after: $from, before: $till}
    ) {
      sender { address }
      receiver { address }
      amount
      amountUSD: amount(in: USD)
      transaction { hash }
      depth
      block { height timestamp { time } }
      currency { symbol }
    }
  }
}
"""


def query_coinpath(address: str, network: str, depth: int, limit: int,
                   date_from: str, date_till: str) -> dict:
    api_key = os.getenv("BITQUERY_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("ERROR: Set BITQUERY_API_KEY in .env file", file=sys.stderr)
        sys.exit(1)

    variables = {
        "network": network,
        "address": address,
        "limit": limit,
        "from": date_from,
        "till": date_till,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    print(f"Querying Bitquery Coinpath API (Bitcoin)...")
    print(f"  Address : {address}")
    print(f"  Network : {network}")
    print(f"  Depth   : {depth}")
    print(f"  Limit   : {limit}/depth")
    print(f"  From    : {date_from}")
    print(f"  Till    : {date_till}")

    print(f"\n  Fetching outbound flows...")
    resp = requests.post(
        BITQUERY_V1_ENDPOINT,
        json={"query": COINPATH_OUTBOUND_QUERY, "variables": variables},
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    outbound_payload = resp.json()
    if "errors" in outbound_payload:
        print(f"API errors (outbound): {json.dumps(outbound_payload['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)

    print(f"  Fetching inbound flows...")
    resp = requests.post(
        BITQUERY_V1_ENDPOINT,
        json={"query": COINPATH_INBOUND_QUERY, "variables": variables},
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    inbound_payload = resp.json()
    if "errors" in inbound_payload:
        print(f"API errors (inbound): {json.dumps(inbound_payload['errors'], indent=2)}", file=sys.stderr)
        sys.exit(1)

    return {
        "bitcoin": {
            "outbound": outbound_payload["data"]["bitcoin"]["outbound"],
            "inbound": inbound_payload["data"]["bitcoin"]["inbound"],
        }
    }


def build_graph(data: dict, initial_address: str):
    """Parse the coinpath JSON into nodes dict and edges list."""
    nodes = {}
    edges = []

    def ensure_node(addr):
        if addr not in nodes:
            nodes[addr] = {"in_btc": 0.0, "out_btc": 0.0, "in_usd": 0.0, "out_usd": 0.0}

    for direction in ("outbound", "inbound"):
        transfers = data.get("bitcoin", {}).get(direction, [])
        if transfers is None:
            transfers = []
        for t in transfers:
            sender = t["sender"]["address"]
            receiver = t["receiver"]["address"]
            amount = t["amount"]
            amount_usd = t.get("amountUSD", 0) or 0
            tx_hash = t["transaction"]["hash"]
            ts = t.get("block", {}).get("timestamp", {}).get("time", "")
            depth = t["depth"]

            ensure_node(sender)
            ensure_node(receiver)
            nodes[sender]["out_btc"] += amount
            nodes[sender]["out_usd"] += amount_usd
            nodes[receiver]["in_btc"] += amount
            nodes[receiver]["in_usd"] += amount_usd

            edges.append({
                "source": sender,
                "target": receiver,
                "amount": amount,
                "amount_usd": amount_usd,
                "tx_hash": tx_hash,
                "timestamp": ts,
                "depth": depth,
            })

    for addr, n in nodes.items():
        if addr == initial_address:
            n["role"] = "source"
        elif n["out_btc"] < 1e-12:
            n["role"] = "sink"
        elif n["in_btc"] < 1e-12:
            n["role"] = "origin"
        else:
            n["role"] = "relay"

    return nodes, edges


def layout_circular(nodes: dict):
    """Assign x,y positions in a circle."""
    n = len(nodes)
    positions = {}
    for i, addr in enumerate(nodes):
        angle = 2 * math.pi * i / n
        positions[addr] = (round(300 * math.cos(angle), 2), round(300 * math.sin(angle), 2))
    return positions


def write_gexf(nodes: dict, edges: list, positions: dict, network: str, output_path: Path):
    """Write a GEXF file compatible with Gephi."""
    GEXF_NS = "http://www.gexf.net/1.2draft"
    VIZ_NS = "http://www.gexf.net/1.2draft/viz"

    gexf = Element("gexf", xmlns=GEXF_NS)
    gexf.set("xmlns:viz", VIZ_NS)
    gexf.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    gexf.set("xsi:schemaLocation", f"{GEXF_NS} {GEXF_NS}/gexf.xsd")
    gexf.set("version", "1.2")

    meta = SubElement(gexf, "meta", lastmodifieddate=datetime.now().strftime("%Y-%m-%d"))
    SubElement(meta, "creator").text = "coinpath_trace.py"
    SubElement(meta, "description").text = "Bitquery Coinpath Bitcoin transaction trace"

    graph = SubElement(gexf, "graph", defaultedgetype="directed", mode="static")

    node_attrs = SubElement(graph, "attributes", **{"class": "node", "mode": "static"})
    for aid, title, atype in [
        ("0", "full_address", "string"), ("1", "chain", "string"),
        ("2", "total_in_btc", "float"), ("3", "total_out_btc", "float"),
        ("4", "total_in_usd", "float"), ("5", "total_out_usd", "float"),
        ("6", "role", "string"),
    ]:
        SubElement(node_attrs, "attribute", id=aid, title=title, type=atype)

    edge_attrs = SubElement(graph, "attributes", **{"class": "edge", "mode": "static"})
    for aid, title, atype in [
        ("0", "tx_hash", "string"), ("1", "amount_btc", "float"),
        ("2", "amount_usd", "float"), ("3", "depth", "integer"),
        ("4", "timestamp", "string"), ("5", "chain", "string"),
    ]:
        SubElement(edge_attrs, "attribute", id=aid, title=title, type=atype)

    ROLE_COLORS = {
        "source": (231, 76, 60),
        "relay": (52, 152, 219),
        "sink": (46, 204, 113),
        "origin": (155, 89, 182),
    }

    nodes_el = SubElement(graph, "nodes")
    addr_to_id = {}
    for i, (addr, ndata) in enumerate(nodes.items()):
        addr_to_id[addr] = str(i)
        short = addr[:6] + "…" + addr[-4:]
        node_el = SubElement(nodes_el, "node", id=str(i), label=short)
        avs = SubElement(node_el, "attvalues")
        SubElement(avs, "attvalue", **{"for": "0", "value": addr})
        SubElement(avs, "attvalue", **{"for": "1", "value": network})
        SubElement(avs, "attvalue", **{"for": "2", "value": str(round(ndata["in_btc"], 8))})
        SubElement(avs, "attvalue", **{"for": "3", "value": str(round(ndata["out_btc"], 8))})
        SubElement(avs, "attvalue", **{"for": "4", "value": str(round(ndata["in_usd"], 2))})
        SubElement(avs, "attvalue", **{"for": "5", "value": str(round(ndata["out_usd"], 2))})
        SubElement(avs, "attvalue", **{"for": "6", "value": ndata["role"]})

        r, g, b = ROLE_COLORS.get(ndata["role"], (149, 165, 166))
        SubElement(node_el, f"{{{VIZ_NS}}}color", r=str(r), g=str(g), b=str(b), a="1.0")

        max_vol = max((n["in_btc"] + n["out_btc"]) for n in nodes.values()) or 1
        vol = ndata["in_btc"] + ndata["out_btc"]
        size = max(10, round(80 * (vol / max_vol), 2))
        SubElement(node_el, f"{{{VIZ_NS}}}size", value=str(size))
        SubElement(node_el, f"{{{VIZ_NS}}}shape", value="disc")

        x, y = positions[addr]
        SubElement(node_el, f"{{{VIZ_NS}}}position", x=str(x), y=str(y), z="0")

    edges_el = SubElement(graph, "edges")
    max_amount = max((e["amount"] for e in edges), default=1) or 1
    for i, e in enumerate(edges):
        weight = round(1 + 9 * math.log1p(e["amount"]) / math.log1p(max_amount), 4)
        edge_el = SubElement(edges_el, "edge", id=str(i),
                             source=addr_to_id[e["source"]], target=addr_to_id[e["target"]],
                             weight=str(weight), type="directed")
        avs = SubElement(edge_el, "attvalues")
        SubElement(avs, "attvalue", **{"for": "0", "value": e["tx_hash"]})
        SubElement(avs, "attvalue", **{"for": "1", "value": str(e["amount"])})
        SubElement(avs, "attvalue", **{"for": "2", "value": str(round(e["amount_usd"], 2))})
        SubElement(avs, "attvalue", **{"for": "3", "value": str(e["depth"])})
        SubElement(avs, "attvalue", **{"for": "4", "value": e["timestamp"]})
        SubElement(avs, "attvalue", **{"for": "5", "value": network})

        dep = e["depth"]
        alpha = max(0.4, 1.0 - (dep - 1) * 0.2)
        SubElement(edge_el, f"{{{VIZ_NS}}}color", r="255", g="165", b="0", a=str(alpha))

    indent(gexf)
    tree = ElementTree(gexf)
    tree.write(str(output_path), xml_declaration=True, encoding="unicode")
    print(f"  GEXF  -> {output_path}")


def write_html(nodes: dict, edges: list, positions: dict, network: str,
               initial_address: str, date_from: str, date_till: str, output_path: Path):
    """Write a self-contained interactive Sigma.js HTML visualization."""

    ROLE_COLORS = {
        "source": "#e74c3c",
        "relay": "#3498db",
        "sink": "#2ecc71",
        "origin": "#9b59b6",
    }

    max_vol = max((n["in_btc"] + n["out_btc"]) for n in nodes.values()) or 1
    min_depth = min((e["depth"] for e in edges), default=1)
    max_depth = max((e["depth"] for e in edges), default=1)
    max_amount = max((e["amount"] for e in edges), default=1) or 1

    js_nodes = []
    addr_to_id = {}
    for i, (addr, ndata) in enumerate(nodes.items()):
        addr_to_id[addr] = str(i)
        short = addr[:6] + "…" + addr[-4:]
        vol = ndata["in_btc"] + ndata["out_btc"]
        size = max(5, round(32 * (vol / max_vol), 1))
        color = ROLE_COLORS.get(ndata["role"], "#95a5a6")
        x, y = positions[addr]
        js_nodes.append(
            f'{{ id:"{i}",label:"{short}",x:{x},y:{y},size:{size},color:"{color}",'
            f'role:"{ndata["role"]}",addr:"{addr}",'
            f'in_btc:{round(ndata["in_btc"],8)},out_btc:{round(ndata["out_btc"],8)},'
            f'in_usd:{round(ndata["in_usd"],2)},out_usd:{round(ndata["out_usd"],2)} }}'
        )

    js_edges = []
    for i, e in enumerate(edges):
        size = max(1, round(6 * math.log1p(e["amount"]) / math.log1p(max_amount), 1))
        alpha = max(0.3, round(0.7 - (e["depth"] - 1) * 0.15, 2))
        g_val = max(100, 165 - (e["depth"] - 1) * 25)
        short_tx = e["tx_hash"][:6] + "…" + e["tx_hash"][-4:] if len(e["tx_hash"]) > 12 else e["tx_hash"]
        js_edges.append(
            f'{{ id:"e{i}",source:"{addr_to_id[e["source"]]}",target:"{addr_to_id[e["target"]]}",'
            f'size:{size},color:"rgba(255,{g_val},0,{alpha})",'
            f'amount:{e["amount"]},usd:{round(e["amount_usd"],2)},'
            f'depth:{e["depth"]},tx:"{short_tx}",ts:"{e["timestamp"]}" }}'
        )

    roles_in_graph = sorted(set(n["role"] for n in nodes.values()))
    legend_items = "\n".join(
        f'    <div class="item"><div class="dot" style="background:{ROLE_COLORS.get(r, "#95a5a6")}"></div> {r.title()}</div>'
        for r in roles_in_graph
    )

    short_addr = initial_address[:6] + "…" + initial_address[-4:]
    date_range = f"{date_from} → {date_till}"

    html = textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8"/>
    <title>Coinpath Trace — {short_addr}</title>
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      body {{ background:#0d1117; color:#c9d1d9; font-family:'JetBrains Mono','SF Mono',monospace; overflow:hidden; }}
      #graph-container {{ width:100vw; height:100vh; }}
      #info-panel {{
        position:fixed; top:16px; left:16px; z-index:10;
        background:rgba(22,27,34,0.92); border:1px solid #30363d; border-radius:10px;
        padding:18px 22px; min-width:270px; backdrop-filter:blur(12px);
      }}
      #info-panel h2 {{ font-size:15px; font-weight:600; color:#58a6ff; margin-bottom:10px; letter-spacing:.5px; }}
      #info-panel .stat {{ font-size:12px; color:#8b949e; margin-bottom:4px; }}
      #info-panel .stat b {{ color:#c9d1d9; }}
      #legend {{ margin-top:14px; }}
      #legend .item {{ display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:5px; }}
      #legend .dot {{ width:12px; height:12px; border-radius:50%; flex-shrink:0; }}
      #tooltip {{
        position:fixed; z-index:20; display:none; pointer-events:none;
        background:rgba(22,27,34,0.95); border:1px solid #30363d; border-radius:8px;
        padding:12px 16px; font-size:12px; max-width:420px; backdrop-filter:blur(12px);
      }}
      #tooltip .addr {{ color:#58a6ff; font-size:11px; word-break:break-all; margin-bottom:6px; }}
      #tooltip .row {{ color:#8b949e; margin-bottom:3px; }}
      #tooltip .row b {{ color:#c9d1d9; }}
      #toast {{
        position:fixed; bottom:24px; left:50%; transform:translateX(-50%); z-index:30;
        background:rgba(46,204,113,0.92); color:#fff; font-size:13px; font-weight:600;
        padding:8px 20px; border-radius:8px; opacity:0; transition:opacity 0.3s;
        pointer-events:none;
      }}
      #toast.show {{ opacity:1; }}
    </style>
    </head>
    <body>
    <div id="graph-container"></div>
    <div id="info-panel">
      <h2>COINPATH TRACE</h2>
      <div class="stat">Address: <b>{short_addr}</b></div>
      <div class="stat">Nodes: <b>{len(nodes)}</b></div>
      <div class="stat">Edges: <b>{len(edges)}</b></div>
      <div class="stat">Depths: <b>{min_depth} – {max_depth}</b></div>
      <div class="stat">Chain: <b>{network.title()}</b></div>
      <div class="stat">Currency: <b>BTC</b></div>
      <div class="stat">Period: <b>{date_range}</b></div>
      <div id="legend">
    {legend_items}
      </div>
      <div class="stat" style="margin-top:10px;color:#58a6ff;font-size:11px;">Click node to copy address</div>
    </div>
    <div id="tooltip"></div>
    <div id="toast"></div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/graphology/0.25.4/graphology.umd.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/sigma.js/2.4.0/sigma.min.js"></script>
    <script>
    const graphData = {{
      nodes: [
        {(","+chr(10)+"    ").join(js_nodes)}
      ],
      edges: [
        {(","+chr(10)+"    ").join(js_edges)}
      ]
    }};

    const graph = new graphology.Graph({{ multi:true, type:"directed" }});
    graphData.nodes.forEach(n => {{
      graph.addNode(n.id, {{ x:n.x, y:n.y, size:n.size, color:n.color, label:n.label,
        role:n.role, addr:n.addr, in_btc:n.in_btc, out_btc:n.out_btc, in_usd:n.in_usd, out_usd:n.out_usd }});
    }});
    graphData.edges.forEach(e => {{
      graph.addEdgeWithKey(e.id, e.source, e.target, {{ size:e.size, color:e.color, type:"arrow",
        amount:e.amount, usd:e.usd, depth:e.depth, tx:e.tx, ts:e.ts }});
    }});

    const container = document.getElementById("graph-container");
    const tooltip = document.getElementById("tooltip");

    function drawLabel(context, data, settings) {{
      if (!data.label) return;
      const size = settings.labelSize || 12;
      const font = settings.labelFont || "sans-serif";
      const weight = settings.labelWeight || "600";
      context.font = weight + " " + size + "px " + font;
      const textWidth = context.measureText(data.label).width;
      const px = 6, py = 3;
      const bx = data.x + data.size + 4;
      const by = data.y - size/2 - py;
      const r = 4, w = textWidth + px*2, h = size + py*2;

      context.fillStyle = "rgba(13,17,23,0.92)";
      context.beginPath();
      context.moveTo(bx+r, by);
      context.lineTo(bx+w-r, by);
      context.quadraticCurveTo(bx+w, by, bx+w, by+r);
      context.lineTo(bx+w, by+h-r);
      context.quadraticCurveTo(bx+w, by+h, bx+w-r, by+h);
      context.lineTo(bx+r, by+h);
      context.quadraticCurveTo(bx, by+h, bx, by+h-r);
      context.lineTo(bx, by+r);
      context.quadraticCurveTo(bx, by, bx+r, by);
      context.closePath();
      context.fill();
      context.strokeStyle = "rgba(88,166,255,0.3)";
      context.lineWidth = 1;
      context.stroke();

      context.fillStyle = "#e6edf3";
      context.fillText(data.label, bx + px, by + size + py - 1);
    }}

    function drawHover(context, data, settings) {{
      drawLabel(context, data, settings);
    }}

    const renderer = new Sigma(graph, container, {{
      defaultEdgeType:"arrow", renderEdgeLabels:false,
      labelFont:"'JetBrains Mono',monospace",
      labelSize:12, labelWeight:"600",
      labelRenderedSizeThreshold: 6,
      labelRenderer: drawLabel,
      hoverRenderer: drawHover,
      stagePadding:60, zIndex:true,
      minCameraRatio:0.2, maxCameraRatio:5,
    }});

    // --- Drag + click-to-copy ---
    let draggedNode = null;
    let isDragging = false;
    let hasMoved = false;
    renderer.on("downNode", (e) => {{
      isDragging = true;
      hasMoved = false;
      draggedNode = e.node;
      graph.setNodeAttribute(draggedNode, "highlighted", true);
      renderer.getCamera().disable();
    }});
    renderer.getMouseCaptor().on("mousemovebody", (e) => {{
      if(!isDragging || !draggedNode) {{
        if(tooltip.style.display==="block") {{
          tooltip.style.left = e.original.clientX+16+"px";
          tooltip.style.top = e.original.clientY+16+"px";
        }}
        return;
      }}
      hasMoved = true;
      const pos = renderer.viewportToGraph(e);
      graph.setNodeAttribute(draggedNode, "x", pos.x);
      graph.setNodeAttribute(draggedNode, "y", pos.y);
    }});
    renderer.getMouseCaptor().on("mouseup", () => {{
      if(draggedNode && !hasMoved) {{
        const addr = graph.getNodeAttribute(draggedNode, "addr");
        navigator.clipboard.writeText(addr).then(() => {{
          const toast = document.getElementById("toast");
          toast.textContent = "Copied " + addr.slice(0,8) + "\u2026" + addr.slice(-4);
          toast.classList.add("show");
          setTimeout(() => toast.classList.remove("show"), 1500);
        }});
      }}
      if(draggedNode) graph.removeNodeAttribute(draggedNode, "highlighted");
      isDragging = false;
      draggedNode = null;
      hasMoved = false;
      renderer.getCamera().enable();
    }});

    // --- Hover highlight ---
    let hoveredNode = null;
    renderer.on("enterNode", ({{ node }}) => {{
      if(isDragging) return;
      hoveredNode = node;
      container.style.cursor = "grab";
      const a = graph.getNodeAttributes(node);
      const fmt = v => v >= 1000 ? v.toLocaleString("en-US",{{maximumFractionDigits:2}}) : v;
      tooltip.innerHTML =
        '<div class="addr">'+a.addr+'</div>'+
        '<div class="row">Role: <b>'+a.role+'</b></div>'+
        '<div class="row">In: <b>'+fmt(a.in_btc)+' BTC</b> ($'+fmt(a.in_usd)+')</div>'+
        '<div class="row">Out: <b>'+fmt(a.out_btc)+' BTC</b> ($'+fmt(a.out_usd)+')</div>';
      tooltip.style.display = "block";
      graph.forEachNode((n) => {{
        graph.setNodeAttribute(n,"highlighted", n===node || graph.areNeighbors(n,node));
      }});
      renderer.refresh();
    }});
    renderer.on("leaveNode", () => {{
      if(isDragging) return;
      hoveredNode = null; tooltip.style.display = "none";
      container.style.cursor = "default";
      graph.forEachNode(n => graph.setNodeAttribute(n,"highlighted",false));
      renderer.refresh();
    }});
    renderer.setSetting("nodeReducer", (node, data) => {{
      const res = {{...data}};
      if(hoveredNode && !graph.getNodeAttribute(node,"highlighted") && node!==hoveredNode) {{
        res.color="#21262d"; res.label="";
      }}
      return res;
    }});
    renderer.setSetting("edgeReducer", (edge, data) => {{
      const res = {{...data}};
      if(hoveredNode) {{
        const s=graph.source(edge), t=graph.target(edge);
        if(s!==hoveredNode && t!==hoveredNode) res.color="rgba(48,54,61,0.3)";
      }}
      return res;
    }});
    </script>
    </body>
    </html>
    """)

    output_path.write_text(html)
    print(f"  HTML  -> {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Trace Bitcoin fund flows using Bitquery Coinpath API and generate Gephi + HTML visualizations."
    )
    parser.add_argument("address", help="Bitcoin address to trace (e.g. bc1q..., 1A1z..., 3J98...)")
    parser.add_argument("--network", required=True,
                        help="Bitcoin network (e.g. bitcoin, litecoin, dogecoin, dash, bitcoincash, bitcoinsv, zcash)")
    parser.add_argument("--from", dest="date_from", required=True,
                        help="Start date (ISO 8601, e.g. 2024-01-01)")
    parser.add_argument("--till", required=True,
                        help="End date (ISO 8601, e.g. 2024-12-31)")
    parser.add_argument("--depth", type=int, default=3,
                        help="Max trace depth in hops (default: 3)")
    parser.add_argument("--limit", type=int, default=25,
                        help="Max results per depth level (default: 25)")
    parser.add_argument("--output", default=None,
                        help="Output filename prefix (default: derived from address)")
    parser.add_argument("--json-input", default=None,
                        help="Skip API, use local JSON file (still need required flags)")

    args = parser.parse_args()
    address = args.address.strip()
    prefix = args.output or f"trace_{address[:8]}_{address[-4:]}"

    script_dir = Path(__file__).parent

    if args.json_input:
        print(f"Loading from local file: {args.json_input}")
        with open(args.json_input) as f:
            data = json.load(f)
    else:
        data = query_coinpath(
            address=address,
            network=args.network,
            depth=args.depth,
            limit=args.limit,
            date_from=args.date_from,
            date_till=args.till,
        )
        json_path = script_dir / f"{prefix}.json"
        json_path.write_text(json.dumps(data, indent=2))
        print(f"  JSON  -> {json_path}")

    outbound = data.get("bitcoin", {}).get("outbound", []) or []
    inbound = data.get("bitcoin", {}).get("inbound", []) or []
    print(f"\nReceived {len(outbound)} outbound + {len(inbound)} inbound transfers")

    if not outbound and not inbound:
        print("No coinpath data returned. Try adjusting depth, date range, or address.")
        sys.exit(0)

    nodes, edges = build_graph(data, address)
    positions = layout_circular(nodes)

    print(f"Graph: {len(nodes)} nodes, {len(edges)} edges\n")
    print("Generating outputs:")
    write_gexf(nodes, edges, positions, args.network, script_dir / f"{prefix}.gexf")
    write_html(nodes, edges, positions, args.network, address,
               args.date_from, args.till, script_dir / f"{prefix}.html")
    print(f"\nDone! Open the .gexf in Gephi or the .html in a browser.")


if __name__ == "__main__":
    main()
