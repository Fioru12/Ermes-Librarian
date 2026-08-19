import { useState } from 'react';
import { Upload } from 'lucide-react';

export default function WorkbookImport({ showNotif }: { showNotif: (m: string, t: 'success' | 'error') => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/formula/import', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        showNotif(`Workbook importato: ${data.formulas_imported} formule`, 'success');
        setFile(null);
      } else {
        showNotif(data.detail || 'Errore importazione', 'error');
      }
    } catch (e) { showNotif('Errore di rete', 'error'); }
    finally { setLoading(false); }
  };

  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow">
      <h2 className="text-xl font-bold mb-4">Importazione Workbook</h2>
      <div className="flex gap-4 items-center">
        <input type="file" onChange={handleFileChange} accept=".md,.txt" className="dark:text-white" />
        <button onClick={handleImport} disabled={!file || loading} 
                className="bg-green-600 text-white p-2 rounded flex items-center gap-2 disabled:bg-gray-400">
          <Upload size={20} /> {loading ? 'Importazione...' : 'Carica Workbook'}
        </button>
      </div>
      {file && <p className="mt-2 text-sm text-gray-500">File selezionato: {file.name}</p>}
    </div>
  );
}
