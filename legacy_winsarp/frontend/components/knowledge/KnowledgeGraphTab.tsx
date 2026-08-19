import { useState, useEffect, useCallback, useRef } from 'react'
import { BookOpen, Share2, ZoomIn, ZoomOut, RefreshCw } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { CardTitle, Input, Button, Badge } from '../../components/ui'
import type { GraphData, GraphNode } from '../../types'

export default function KnowledgeGraphTab() {
  const { t, isDark } = useTheme()
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [zoom, setZoom] = useState(1)
  const svgRef = useRef<SVGSVGElement>(null)
  const [dragNode, setDragNode] = useState<string | null>(null)
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>({})
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const fetchGraph = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/graph')
      if (res.ok) setGraph(await res.json())
    } catch { setGraph(null) }
    setLoading(false)
  }

  useEffect(() => { fetchGraph() }, [])

  const initPositions = useCallback(() => {
    if (!graph) return
    const positions: Record<string, { x: number; y: number }> = {}
    const centerX = 350
    const centerY = 300
    graph.nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / graph.nodes.length
      const radius = 180 + (graph.nodes.length > 10 ? 60 : 0)
      positions[node.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      }
    })
    setNodePositions(positions)
  }, [graph])

  useEffect(() => { initPositions() }, [initPositions])

  const filteredNodes = graph?.nodes.filter(n => {
    if (!searchTerm) return true
    const t = searchTerm.toLowerCase()
    return n.id.toLowerCase().includes(t) || (n.name || '').toLowerCase().includes(t) || (n.tipo || '').toLowerCase().includes(t)
  }) || []

  const filteredLinks = graph?.links.filter(l =>
    filteredNodes.some(n => n.id === l.source) && filteredNodes.some(n => n.id === l.target)
  ) || []

  const getNodeColor = (node: GraphNode) => {
    switch (node.tipo) {
      case 'base': return isDark ? '#3b82f6' : '#2563eb'
      case 'scostamento': return isDark ? '#f59e0b' : '#d97706'
      case 'maggiorazione': return isDark ? '#10b981' : '#059669'
      case 'personalizzata': return isDark ? '#8b5cf6' : '#7c3aed'
      default: return isDark ? '#64748b' : '#475569'
    }
  }

  const handleNodeDrag = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault()
    setDragNode(nodeId)
  }

  useEffect(() => {
    if (!dragNode) return
    const handleMove = (e: MouseEvent) => {
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      setNodePositions(prev => ({
        ...prev,
        [dragNode]: {
          x: (e.clientX - rect.left) / zoom,
          y: (e.clientY - rect.top) / zoom,
        }
      }))
    }
    const handleUp = () => setDragNode(null)
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [dragNode, zoom])

  if (loading) return <div className={`flex-1 flex items-center justify-center ${t.chatBg}`}>
    <RefreshCw className="w-8 h-8 text-slate-500 animate-spin" />
  </div>

  const graphSize = 700 * zoom

  return (
    <div className={`flex h-full ${t.chatBg}`}>
      {/* Graph */}
      <div className="flex-1 flex flex-col">
        <div className={`flex items-center gap-3 px-6 py-4 border-b ${t.documentsBg}`}>
          <CardTitle><BookOpen className="w-4 h-4 text-indigo-400" />Knowledge Graph</CardTitle>
          <div className="flex-1 max-w-xs ml-4">
            <Input placeholder="Cerca nel grafo..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => setZoom(z => Math.min(z + 0.2, 3))} className={`p-1.5 rounded-lg transition cursor-pointer ${t.navButtonInactive}`}>
              <ZoomIn className="w-4 h-4" />
            </button>
            <button onClick={() => setZoom(z => Math.max(z - 0.2, 0.4))} className={`p-1.5 rounded-lg transition cursor-pointer ${t.navButtonInactive}`}>
              <ZoomOut className="w-4 h-4" />
            </button>
            <button onClick={initPositions} className={`p-1.5 rounded-lg transition cursor-pointer ${t.navButtonInactive}`}>
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-4" style={{ minHeight: 0 }}>
          <svg ref={svgRef} viewBox={`0 0 ${graphSize} ${graphSize}`} className="w-full h-full">
            <defs>
              {graph?.links.map((link, i) => {
                let markerId: string
                if (link.rel === 'dipende da') { markerId = `arrow-dep-${i}` }
                else if (link.rel === 'contiene') { markerId = `arrow-contains-${i}` }
                else { markerId = `arrow-${i}` }
                return (
                  <marker key={i} id={markerId} viewBox="0 0 10 10" refX={10} refY={5} markerWidth={6} markerHeight={6} orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={isDark ? '#64748b' : '#94a3b8'} />
                  </marker>
                )
              })}
            </defs>
            {filteredLinks.map((link, i) => {
              const s = nodePositions[link.source]
              const t = nodePositions[link.target]
              if (!s || !t) return null
              const highlight = selectedNode && (link.source === selectedNode.id || link.target === selectedNode.id)
              const mx = (s.x + t.x) / 2
              const my = (s.y + t.y) / 2
              let markerId: string
              if (link.rel === 'dipende da') { markerId = `arrow-dep-${i}` }
              else if (link.rel === 'contiene') { markerId = `arrow-contains-${i}` }
              else { markerId = `arrow-${i}` }
              return (
                <g key={i}>
                  <line x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                    stroke={highlight ? '#3b82f6' : (isDark ? '#334155' : '#cbd5e1')}
                    strokeWidth={highlight ? 2.5 : 1.5}
                    markerEnd={`url(#${markerId})`} />
                  <text x={mx + 8} y={my - 8} textAnchor="middle" className="text-[9px]"
                    fill={isDark ? '#94a3b8' : '#64748b'}>{link.rel}</text>
                </g>
              )
            })}
            {filteredNodes.map(node => {
              const pos = nodePositions[node.id]
              if (!pos) return null
              const color = getNodeColor(node)
              const isSelected = selectedNode?.id === node.id
              const isHovered = hoveredNode === node.id
              const radius = isSelected ? 22 : (isHovered ? 18 : 14)
              return (
                <g key={node.id}
                  onMouseDown={e => handleNodeDrag(e, node.id)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => setSelectedNode(node)}
                  className="cursor-grab active:cursor-grabbing"
                  style={{ cursor: 'pointer' }}>
                  <circle cx={pos.x} cy={pos.y} r={radius}
                    fill={color} fillOpacity={0.2}
                    stroke={color} strokeWidth={isSelected ? 3 : 2}
                    filter={isSelected ? 'drop-shadow(0 0 6px rgba(59,130,246,0.5))' : undefined} />
                  <text x={pos.x} y={pos.y} textAnchor="middle" dominantBaseline="central"
                    className="text-[10px] font-bold pointer-events-none select-none"
                    fill={color}>{node.id}</text>
                  <text x={pos.x} y={pos.y + radius + 12} textAnchor="middle"
                    className="text-[9px] pointer-events-none select-none"
                    fill={isDark ? '#cbd5e1' : '#334155'}>{node.name || node.id}</text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>

      {/* Sidebar */}
      {selectedNode && (
        <div className={`w-80 border-l p-6 overflow-y-auto ${t.documentsBg}`}>
          <CardTitle>{selectedNode.id}</CardTitle>
          <div className="space-y-4 mt-4">
            <div>
              <div className="text-xs font-semibold text-slate-400 mb-1">Nome</div>
              <p className="text-sm">{selectedNode.name || '-'}</p>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-400 mb-1">Tipo</div>
              <Badge color={selectedNode.tipo === 'base' ? 'blue' : selectedNode.tipo === 'scostamento' ? 'amber' : selectedNode.tipo === 'maggiorazione' ? 'emerald' : 'purple'}>{selectedNode.tipo || '-'}</Badge>
            </div>
            {selectedNode.categoria && <div>
              <div className="text-xs font-semibold text-slate-400 mb-1">Categoria</div>
              <p className="text-sm">{selectedNode.categoria}</p>
            </div>}
            {selectedNode.descrizione && <div>
              <div className="text-xs font-semibold text-slate-400 mb-1">Descrizione</div>
              <p className="text-sm text-slate-300">{selectedNode.descrizione}</p>
            </div>}
            <div>
              <div className="text-xs font-semibold text-slate-400 mb-1">Connessioni</div>
              <div className="space-y-1">
                {filteredLinks.filter(l => l.source === selectedNode.id).map((l, i) => (
                  <div key={i} className="text-xs text-slate-400 flex items-center gap-1">
                    <Share2 className="w-3 h-3 text-blue-400" /> → {l.target} <span className="italic">({l.rel})</span>
                  </div>
                ))}
                {filteredLinks.filter(l => l.target === selectedNode.id).map((l, i) => (
                  <div key={i} className="text-xs text-slate-400 flex items-center gap-1">
                    ← {l.source} <span className="italic">({l.rel})</span>
                  </div>
                ))}
              </div>
            </div>
            <Button variant="secondary" onClick={() => setSelectedNode(null)}>Chiudi</Button>
          </div>
        </div>
      )}
    </div>
  )
}
