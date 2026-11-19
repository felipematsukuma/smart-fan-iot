export interface CommandState {
  status: 'pending' | 'confirmed' | 'failed';
  ack_event_id?: string | null;
  execution_unknown: boolean;
}
export function commandPresentation(
  command: CommandState | undefined,
  sending = false,
) {
  if (sending)
    return {
      label: 'Enviando solicitação',
      detail: 'Aguardando resposta da API.',
      tone: 'neutral' as const,
    };
  if (!command)
    return {
      label: 'Nenhum comando selecionado',
      detail: 'O estado observado aparece separadamente.',
      tone: 'neutral' as const,
    };
  if (command.execution_unknown)
    return {
      label: 'Execução desconhecida',
      detail:
        'Sem confirmação física no prazo. Confira as próximas leituras antes de enviar outra intenção.',
      tone: 'warning' as const,
    };
  if (command.status === 'confirmed' && command.ack_event_id)
    return {
      label: 'Executado pelo dispositivo',
      detail:
        'Confirmação física validada. Confira o estado nas leituras seguintes.',
      tone: 'good' as const,
    };
  if (command.status === 'pending')
    return {
      label: 'Aceito pela API · aguardando execução',
      detail:
        'Intenção registrada. Entrega intermediária ou recebimento pelo broker não confirma execução.',
      tone: 'neutral' as const,
    };
  return {
    label: 'Sem execução confirmada',
    detail:
      'Consulte o retorno e o estado observado. Nenhum estado físico foi presumido.',
    tone: 'warning' as const,
  };
}
