"""Test nuove feature knowledge graph."""
import sys
sys.path.insert(0, "C:\\ProgettoRAG_DEV")
from core.knowledge_graph import rebuild

g = rebuild()
s = g.stats()
print(f"Grafo: {s}")

print("\n=== find_by_field_op('T') ===")
for n in g.find_by_field_op("T"):
    print(f"  #{n['id']}: {n['name'][:50]} -> T() fields: {n['field_ops'].get('T', [])}")

print("\n=== find_by_field_op('S') ===")
for n in g.find_by_field_op("S"):
    print(f"  #{n['id']}: {n['name'][:50]} -> S() fields: {n['field_ops'].get('S', [])}")

print("\n=== find_by_field_op('S0') ===")
for n in g.find_by_field_op("S0"):
    print(f"  #{n['id']}: {n['name'][:50]} -> S0() fields: {n['field_ops'].get('S0', [])}")

print("\n=== find_by_field_op('N') ===")
for n in g.find_by_field_op("N"):
    print(f"  #{n['id']}: {n['name'][:50]} -> N() fields: {n['field_ops'].get('N', [])}")

print("\n=== rounding ===")
for n in g.find_by_rounding():
    print(f"  #{n['id']}: {n['name'][:50]} -> @{n['rounding']}")

print("\n=== find_by_comparison(field=561) ===")
for n in g.find_by_comparison(561):
    cmps = n.get("comparisons", {}).get(561, [])
    print(f"  #{n['id']}: {n['name'][:50]} -> {cmps}")

print("\n=== find_by_comparison(field=4) ===")
for n in g.find_by_comparison(4):
    cmps = n.get("comparisons", {}).get(4, [])
    print(f"  #{n['id']}: {n['name'][:50]} -> {cmps}")
