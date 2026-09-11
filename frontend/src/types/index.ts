export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  evidence?: { coverage: 'supported' | 'partially_supported' | 'insufficient_evidence'; reason?: string | null }
  feedback?: 1 | -1 | null
  // La domanda che il sistema ha davvero cercato, quando una domanda di
  // raffinamento e' stata riscritta con la conversazione. Va mostrata: chi
  // legge deve poter vedere cosa e' stato chiesto ai documenti.
  searchedAs?: string | null
  sources?: Array<{
    document_id: string; filename: string; version: number; locator: string; excerpt: string
    marker?: number; content_hash?: string; chunk_id?: string; relevance_score?: number
    // Il passaggio contiene istruzioni rivolte al modello: la fonte si mostra,
    // il suo testo non e' stato usato per rispondere.
    injection_suspected?: boolean
  }>
}

export interface DocumentFile {
  name: string
  size?: string
  size_kb?: number
}

export interface HealthStatus {
  status: string
  ollama_ok?: boolean
  ollama_message?: string
  modules_available?: string[]
  chroma_ok?: boolean
  disk_free_gb?: number
}

export interface GraphNode {
  id: string
  label?: string
  name?: string
  group?: string
  tipo?: string
  categoria?: string
  descrizione?: string
}

export interface GraphLink {
  source: string
  target: string
  label?: string
  rel?: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

export interface ProviderConfig {
  name: string
  type: string
  api_key: string
  base_url: string
  default_model: string
  models: string[]
  enabled: boolean
  is_active?: boolean
}

export type TabId = 'chat' | 'docs' | 'kb' | 'health' | 'providers' | 'settings' | 'connectors' | 'admin-users' | 'admin-audit' | 'admin-import' | 'admin-analytics'

export interface ThemeClasses {
  bg: string
  sidebar: string
  sidebarTitle: string
  sidebarLabel: string
  sidebarInput: string
  navButtonActive: string
  navButtonInactive: string
  header: string
  chatBg: string
  welcomeTitle: string
  card: string
  cardTitle: string
  cardDesc: string
  chatBubbleUser: string
  chatBubbleAssistant: string
  chatFormBg: string
  chatInput: string
  statusFooter: string
  tableHeader: string
  tableRow: string
  documentsBg?: string
  docSelected?: string
  skeleton?: string
  textSecondary?: string
  badgeInfo?: string
}
