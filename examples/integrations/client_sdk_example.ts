/**
 * Client TypeScript minimo per le API di Ermes Knowledge (Node 18+ o browser).
 *
 * Tipi e nomi degli eventi corrispondono a quanto restituito da
 * api/libraries.py: vedi docs/INTEGRATION_GUIDE.md.
 */

export interface Citation {
  document_id: string;
  filename: string;
  version: number;
  content_hash: string;
  chunk_id: string;
  locator: string;
  excerpt: string;
  marker: number;
  relevance_score: number;
  injection_suspected: boolean;
}

export interface AskResponse {
  answer_id: string;
  library: { id: string; name: string };
  question: string;
  answer: string;
  status: "answered" | "abstained";
  evidence: { coverage: string; reason: string };
  citations: Citation[];
  meta: Record<string, unknown>;
}

export interface LibraryItem {
  id: string;
  name: string;
  description: string;
  visibility: string;
}

export type StreamEvent =
  | { event: "status"; data: { step: string } }
  | { event: "citations"; data: { citations: Citation[] } }
  | { event: "answer"; data: { chunk: string } }
  | { event: "done"; data: AskResponse }
  | { event: "error"; data: { detail: string } };

export class ErmesClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;

  constructor(options: { baseUrl?: string; apiKey: string }) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8502").replace(/\/$/, "");
    this.apiKey = options.apiKey;
  }

  private async post(path: string, body: unknown): Promise<Response> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${path} → ${res.status}: ${await res.text()}`);
    return res;
  }

  async listLibraries(): Promise<LibraryItem[]> {
    const res = await fetch(`${this.baseUrl}/api/libraries`, {
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!res.ok) throw new Error(`/api/libraries → ${res.status}: ${await res.text()}`);
    return ((await res.json()) as { items: LibraryItem[] }).items;
  }

  async ask(libraryId: string, question: string, topK = 3): Promise<AskResponse> {
    const res = await this.post(`/api/libraries/${encodeURIComponent(libraryId)}/ask`, {
      question,
      top_k: topK,
    });
    return (await res.json()) as AskResponse;
  }

  /** Emette gli eventi SSE già decodificati; l'ultimo è sempre `done` o `error`. */
  async *askStream(libraryId: string, question: string, topK = 3): AsyncGenerator<StreamEvent> {
    const res = await this.post(`/api/libraries/${encodeURIComponent(libraryId)}/ask/stream`, {
      question,
      top_k: topK,
    });
    if (!res.body) throw new Error("Risposta senza corpo");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Un evento SSE termina con una riga vuota; un chunk di rete può
      // contenerne mezzo, quindi si tiene il resto nel buffer.
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        let data = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (data) yield { event, data: JSON.parse(data) } as StreamEvent;
      }
    }
  }
}

// Uso:
//
//   const client = new ErmesClient({ apiKey: process.env.ERMES_API_KEY! });
//   const [lib] = await client.listLibraries();
//   for await (const ev of client.askStream(lib.id, "Entro quando va consegnata la nota spese?")) {
//     if (ev.event === "answer") process.stdout.write(ev.data.chunk);
//     if (ev.event === "done" && ev.data.status === "abstained") console.log("Nessuna evidenza.");
//   }
