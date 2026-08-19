import { useState, useEffect } from 'react';
import { Check, Copy, KeyRound, Trash2, UserPlus, X } from 'lucide-react';

interface User {
  username: string;
  role: string;
  created_at: string;
}

interface LocalAccount {
  username: string;
  role: string;
  active: boolean;
}

interface LocalAccountDraft {
  role: string;
  active: boolean;
  password: string;
}

export default function UserManagement({ showNotif }: { showNotif: (m: string, t: 'success' | 'error') => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [accounts, setAccounts] = useState<LocalAccount[]>([]);
  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState('viewer');
  const [newAccountUsername, setNewAccountUsername] = useState('');
  const [newAccountRole, setNewAccountRole] = useState('viewer');
  const [newAccountPassword, setNewAccountPassword] = useState('');
  const [creatingAccount, setCreatingAccount] = useState(false);
  const [accountDrafts, setAccountDrafts] = useState<Record<string, LocalAccountDraft>>({});
  const [updatingAccount, setUpdatingAccount] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<{ username: string; value: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchUsers = async () => {
    try {
      const res = await fetch('/api/users');
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users || []);
      }
    } catch (e) { showNotif('Errore nel caricamento utenti', 'error'); }
  };

  const fetchAccounts = async () => {
    try {
      const res = await fetch('/api/accounts');
      if (res.ok) {
        const data = await res.json();
        setAccounts(data.users || []);
      }
    } catch { showNotif('Errore nel caricamento account locali', 'error'); }
  };

  useEffect(() => { fetchUsers(); fetchAccounts(); }, []);

  const createLocalAccount = async () => {
    if (!newAccountUsername.trim() || !newAccountPassword) return;
    setCreatingAccount(true);
    try {
      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: newAccountUsername, role: newAccountRole, password: newAccountPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Errore creazione account');
      setNewAccountUsername('');
      setNewAccountPassword('');
      await fetchAccounts();
      showNotif('Account locale creato. Comunica la password con un canale sicuro.', 'success');
    } catch (error) {
      showNotif(error instanceof Error ? error.message : 'Errore richiesta', 'error');
    } finally {
      setCreatingAccount(false);
    }
  };

  const accountDraft = (account: LocalAccount): LocalAccountDraft => accountDrafts[account.username] || {
    role: account.role,
    active: account.active,
    password: '',
  };

  const setAccountDraft = (account: LocalAccount, change: Partial<LocalAccountDraft>) => {
    setAccountDrafts(current => ({ ...current, [account.username]: { ...accountDraft(account), ...change } }));
  };

  const updateLocalAccount = async (account: LocalAccount) => {
    const draft = accountDraft(account);
    setUpdatingAccount(account.username);
    try {
      const payload: Record<string, unknown> = { role: draft.role, active: draft.active };
      if (draft.password) payload.password = draft.password;
      const res = await fetch(`/api/accounts/${encodeURIComponent(account.username)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Errore aggiornamento account');
      setAccountDrafts(current => {
        const next = { ...current };
        delete next[account.username];
        return next;
      });
      await fetchAccounts();
      showNotif('Account locale aggiornato. Le sessioni esistenti sono state revocate.', 'success');
    } catch (error) {
      showNotif(error instanceof Error ? error.message : 'Errore richiesta', 'error');
    } finally {
      setUpdatingAccount(null);
    }
  };

  const createUser = async () => {
    try {
      const res = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: newUsername, role: newRole }),
      });
      const data = await res.json();
      if (res.ok) {
        setRevealedKey({ username: data.username, value: data.api_key });
        setCopied(false);
        showNotif('Chiave API creata: copiala ora, non sarà più mostrata.', 'success');
        setNewUsername('');
        fetchUsers();
      } else {
        showNotif(data.detail || 'Errore creazione', 'error');
      }
    } catch (e) { showNotif('Errore richiesta', 'error'); }
  };

  const copyRevealedKey = async () => {
    if (!revealedKey) return;
    try {
      await navigator.clipboard.writeText(revealedKey.value);
      setCopied(true);
    } catch {
      showNotif('Copia non disponibile: seleziona e copia manualmente la chiave.', 'error');
    }
  };

  const deleteUser = async (username: string) => {
    if (!confirm(`Revocare accesso a ${username}?`)) return;
    try {
      const res = await fetch(`/api/users/${username}`, { method: 'DELETE' });
      if (res.ok) {
        showNotif('Utente revocato', 'success');
        fetchUsers();
      } else {
        showNotif('Errore revoca', 'error');
      }
    } catch (e) { showNotif('Errore richiesta', 'error'); }
  };

  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow">
      <section className="mb-8 border-b border-slate-200 pb-7 dark:border-slate-700">
        <h2 className="text-xl font-bold mb-1">Account web locali</h2>
        <p className="mb-4 text-sm text-slate-500">Crea l’accesso all’interfaccia per chi dovrà consultare o gestire le biblioteche. Le password non vengono mostrate, registrate nei log o salvate nel browser.</p>
        <div className="flex flex-wrap gap-2">
          <input className="border rounded p-2 flex-1 min-w-40 dark:bg-gray-700" placeholder="Username account" value={newAccountUsername} onChange={(e) => setNewAccountUsername(e.target.value)} />
          <select aria-label="Ruolo account locale" className="border rounded p-2 dark:bg-gray-700" value={newAccountRole} onChange={(e) => setNewAccountRole(e.target.value)}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option></select>
          <input aria-label="Password account locale" type="password" className="border rounded p-2 flex-1 min-w-48 dark:bg-gray-700" placeholder="Password iniziale" value={newAccountPassword} onChange={(e) => setNewAccountPassword(e.target.value)} autoComplete="new-password" />
          <button onClick={createLocalAccount} disabled={!newAccountUsername.trim() || !newAccountPassword || creatingAccount} className="bg-blue-600 disabled:opacity-50 text-white p-2 rounded flex items-center gap-2"><UserPlus size={20} />{creatingAccount ? 'Creazione...' : 'Crea account'}</button>
        </div>
        <p className="mt-2 text-xs text-slate-500">Minimo 8 caratteri, maiuscola, minuscola, numero e carattere speciale.</p>
        {accounts.length > 0 && <div className="mt-4 space-y-3">
          {accounts.map(account => {
            const draft = accountDraft(account);
            return <div key={account.username} className="rounded-lg border border-slate-200 p-3 dark:border-slate-600">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><strong>{account.username}</strong><span className="text-xs text-slate-500">{account.active ? 'attivo' : 'disattivato'}</span></div>
              <div className="flex flex-wrap items-center gap-2">
                <select aria-label={`Ruolo di ${account.username}`} className="border rounded p-2 text-sm dark:bg-gray-700" value={draft.role} onChange={(e) => setAccountDraft(account, { role: e.target.value })}><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option></select>
                <label className="flex items-center gap-1 text-sm"><input aria-label={`Accesso attivo per ${account.username}`} type="checkbox" checked={draft.active} onChange={(e) => setAccountDraft(account, { active: e.target.checked })} />Accesso attivo</label>
                <input aria-label={`Nuova password per ${account.username}`} type="password" className="border rounded p-2 text-sm dark:bg-gray-700" placeholder="Nuova password (opzionale)" value={draft.password} onChange={(e) => setAccountDraft(account, { password: e.target.value })} autoComplete="new-password" />
                <button aria-label={`Salva account ${account.username}`} onClick={() => updateLocalAccount(account)} disabled={updatingAccount === account.username} className="rounded bg-slate-700 px-3 py-2 text-sm text-white disabled:opacity-50">{updatingAccount === account.username ? 'Salvataggio...' : 'Salva'}</button>
              </div>
            </div>;
          })}
        </div>}
      </section>
      <h2 className="text-xl font-bold mb-1">Chiavi API (accesso programmatico)</h2>
      <p className="mb-4 text-sm text-slate-500">Questa sezione gestisce chiavi per API e integrazioni, non account con password per l'interfaccia web.</p>
      
      <div className="flex gap-2 mb-6">
        <input 
          className="border rounded p-2 flex-grow dark:bg-gray-700"
          placeholder="Username"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
        />
        <select className="border rounded p-2 dark:bg-gray-700" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
          <option value="viewer">Viewer</option>
          <option value="editor">Editor</option>
          <option value="admin">Admin</option>
        </select>
        <button onClick={createUser} className="bg-blue-600 text-white p-2 rounded flex items-center gap-2">
          <UserPlus size={20} /> Crea
        </button>
      </div>

      <table className="w-full text-left">
        <thead>
          <tr className="border-b">
            <th className="p-2">Username</th>
            <th className="p-2">Ruolo</th>
            <th className="p-2">Azioni</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.username} className="border-b">
              <td className="p-2">{u.username}</td>
              <td className="p-2 capitalize">{u.role}</td>
              <td className="p-2 flex gap-2">
                <button onClick={() => deleteUser(u.username)} className="text-red-500"><Trash2 size={18} /></button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {revealedKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-6" role="dialog" aria-modal="true" aria-label="Nuova chiave API">
          <section className="w-full max-w-xl rounded-2xl border border-amber-400/30 bg-slate-900 p-6 text-slate-100 shadow-2xl">
            <div className="flex items-start justify-between gap-4"><div><h3 className="flex items-center gap-2 text-lg font-semibold"><KeyRound className="h-5 w-5 text-amber-300" />Nuova chiave API</h3><p className="mt-2 text-sm text-slate-400">Questa chiave per <strong className="text-slate-200">{revealedKey.username}</strong> sarà mostrata solo ora. Conservala in un password manager o secret manager, mai in un documento o in Git.</p></div><button onClick={() => setRevealedKey(null)} aria-label="Chiudi chiave API" className="rounded-md p-1 text-slate-400 hover:bg-white/10 hover:text-white"><X className="h-5 w-5" /></button></div>
            <code className="mt-5 block break-all rounded-lg border border-white/10 bg-black/30 p-3 text-sm text-amber-100">{revealedKey.value}</code>
            <div className="mt-5 flex justify-end gap-3"><button onClick={copyRevealedKey} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"><span className="flex items-center gap-2">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? 'Copiata' : 'Copia chiave'}</span></button><button onClick={() => setRevealedKey(null)} className="rounded-lg border border-white/10 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-white/5">Ho salvato la chiave</button></div>
          </section>
        </div>
      )}
    </div>
  );
}
