"""/health non deve girare sul ciclo degli eventi.

Il controllo fa I/O sincrono (httpx verso Ollama con timeout di 3 s, disco,
database). Dichiarato `async def`, lo eseguiva sul ciclo degli eventi: finche'
Ollama rispondeva, il server non serviva NESSUN'altra richiesta - file statici
e API incluse. L'interfaccia sonda /health di continuo, quindi ogni scheda
impiegava da 2 a 6 secondi ad aprirsi. Misurato aprendo le schede con
Playwright: i file statici (2 ms a riposo) arrivavano dopo 2,3 s.

Una funzione `def` viene eseguita da FastAPI in un thread; il test fissa che
non torni `async def` senza accorgersene.
"""

import inspect

from api import health


def test_health_handlers_are_sync_so_they_run_in_the_threadpool():
    assert not inspect.iscoroutinefunction(health.health_check)
    assert not inspect.iscoroutinefunction(health.health_check_v1)
