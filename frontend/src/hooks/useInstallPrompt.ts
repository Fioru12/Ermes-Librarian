import { useCallback, useEffect, useState } from 'react'

/** L'evento non e' ancora nei tipi standard di TypeScript: lo descriviamo noi. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/**
 * Permette di proporre "Installa come app" quando il browser lo consente (Edge e Chrome,
 * dopo che il manifest e' valido). Una volta installata, o se il browser non la offre,
 * `canInstall` e' falso e il pulsante non compare.
 */
export function useInstallPrompt() {
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      event.preventDefault()
      setPromptEvent(event as BeforeInstallPromptEvent)
    }
    const onInstalled = () => setPromptEvent(null)
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const install = useCallback(async () => {
    if (!promptEvent) return
    await promptEvent.prompt()
    setPromptEvent(null)
  }, [promptEvent])

  return { canInstall: promptEvent !== null, install }
}
