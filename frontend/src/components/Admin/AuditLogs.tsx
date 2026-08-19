import { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react';

interface AuditEntry {
  ts: string;
  action: string;
  actor: string;
  detail: any;
}

export default function AuditLogs({ showNotif }: { showNotif: (m: string, t: 'success' | 'error') => void }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [integrity, setIntegrity] = useState<{tampered: number, integrity_ok: boolean} | null>(null);

  const fetchLogs = async () => {
    try {
      const res = await fetch('/api/audit/logs?limit=50');
      if (res.ok) {
        const data = await res.json();
        setEntries(data.entries || []);
      }
      
      const verRes = await fetch('/api/audit/verify');
      if (verRes.ok) {
        setIntegrity(await verRes.json());
      }
    } catch (e) { showNotif('Errore caricamento audit', 'error'); }
  };

  useEffect(() => { fetchLogs(); }, []);

  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow">
      <div className="flex justify-between mb-4">
        <h2 className="text-xl font-bold">Audit Log Amministrativo</h2>
        <button onClick={fetchLogs} className="text-blue-500"><RefreshCw size={20} /></button>
      </div>

      {integrity && (
        <div className={`p-3 mb-4 rounded flex items-center gap-2 ${integrity.integrity_ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {integrity.integrity_ok ? <ShieldCheck /> : <ShieldAlert />}
          {integrity.integrity_ok ? 'Integrità log verificata' : `ATTENZIONE: ${integrity.tampered} log manomessi!`}
        </div>
      )}

      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b bg-gray-50 dark:bg-gray-900">
              <th className="p-2">Timestamp</th>
              <th className="p-2">Azione</th>
              <th className="p-2">Attore</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i} className="border-b hover:bg-gray-50 dark:hover:bg-gray-700">
                <td className="p-2">{new Date(e.ts).toLocaleString()}</td>
                <td className="p-2 font-mono">{e.action}</td>
                <td className="p-2">{e.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
