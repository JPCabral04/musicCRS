export type ChatMessageButton = {
  title: string;
  payload: string;
  button_type: string;
};

export type ChatMessageAttachment = {
  type: string;
  payload: {
    images?: string[];
    buttons?: ChatMessageButton[];
  };
};

// One annotation of a dialogue act, as DialogueKit sends it: {"slot": "option", "value": "1. Love — Keyshia Cole"}.
export type ChatMessageAnnotation = {
  slot: string;
  value: string;
};

// One dialogue act of an agent message, for example OPTIONS or PLAYLIST.
export type ChatMessageDialogueAct = {
  intent: string;
  annotations?: ChatMessageAnnotation[];
};

export type ChatMessage = {
  attachments?: ChatMessageAttachment[];
  text?: string;
  intent?: string;
  dialogue_acts?: ChatMessageDialogueAct[];
};

export type AgentMessage = {
  recipient: string;
  message: ChatMessage;
  info?: string;
};

export type UserMessage = {
  message: string;
};
