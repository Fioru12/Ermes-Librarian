import sys; sys.path.insert(0, '.')
from legacy_winsarp.core.winsarp.knowledge_graph import build_graph, save_graph
print("Building graph...")
graph = build_graph()
save_graph(graph)
print(f"Done: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
for fid in [3000, 3001, 3002, 3003, 3004, 3005, 2100, 2101]:
    n = graph["nodes"].get(fid)
    if n:
        print(f"  {fid}: {n['name']} | tipo={n['tipo']} | code_len={len(n['code'])}")
    else:
        print(f"  {fid}: NOT FOUND")
