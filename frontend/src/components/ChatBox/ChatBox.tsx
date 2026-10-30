import "./ChatBox.css";

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useContext,
} from "react";
import QuickReplyButton from "../QuickReply";
import { useSocket } from "../../contexts/SocketContext";
import { UserContext } from "../../contexts/UserContext";
import {
  MDBCard,
  MDBCardHeader,
  MDBCardBody,
  MDBIcon,
  MDBCardFooter,
} from "mdb-react-ui-kit";
import { AgentChatMessage, UserChatMessage } from "../ChatMessage";
import { ChatMessage } from "../../types";
import { ConfigContext } from "../../contexts/ConfigContext";
import { PlaylistPanel } from "../Playlist/PlaylistPanel";

export default function ChatBox() {
  const { config } = useContext(ConfigContext);
  const { user } = useContext(UserContext);
  const {
    startConversation,
    sendMessage,
    quickReply,
    onMessage,
    onRestart,
    giveFeedback,
  } = useSocket();
  const [chatMessages, setChatMessages] = useState<JSX.Element[]>([]);
  const [chatButtons, setChatButtons] = useState<JSX.Element[]>([]);
  const [inputValue, setInputValue] = useState<string>("");
  const [rawMessages, setRawMessages] = useState<ChatMessage[]>([]);
  
  const chatMessagesRef = useRef(chatMessages);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    startConversation();
  }, [startConversation]);

  const updateMessages = (message: JSX.Element) => {
    chatMessagesRef.current = [...chatMessagesRef.current, message];
    setChatMessages(chatMessagesRef.current);
  };

  const handleInput = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (inputValue.trim() === "") return;
    updateMessages(
      <UserChatMessage
        key={chatMessagesRef.current.length}
        message={inputValue}
      />
    );
    sendMessage({ message: inputValue });
    setInputValue("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const handleSendMessageString = (msgText: string) => {
    if (msgText.trim() === "") return;
    updateMessages(
      <UserChatMessage
        key={chatMessagesRef.current.length}
        message={msgText}
      />
    );
    sendMessage({ message: msgText });
  };

  const handleQuickReply = useCallback(
    (message: string) => {
      updateMessages(
        <UserChatMessage
          key={chatMessagesRef.current.length}
          message={message}
        />
      );
      quickReply({ message: message });
    },
    [chatMessagesRef, quickReply]
  );

  const handelMessage = useCallback(
    (message: ChatMessage) => {
      if (!!message.text) {
        const image_url = message.attachments?.find(
          (attachment) => attachment.type === "images"
        )?.payload.images?.[0];
        updateMessages(
          <AgentChatMessage
            key={chatMessagesRef.current.length}
            feedback={config.useFeedback ? giveFeedback : null}
            message={message.text}
            image_url={image_url}
            dialogue_acts={message.dialogue_acts}
          />
        );
      }
    },
    [giveFeedback, chatMessagesRef, config]
  );

  // A click on an option button: show the option in the chat, send "/select <n>" to the agent.
  const handleOptionClick = useCallback(
    (label: string, command: string) => {
      updateMessages(
        <UserChatMessage key={chatMessagesRef.current.length} message={label} />
      );
      quickReply({ message: command });
    },
    [chatMessagesRef, quickReply]
  );

  const handleButtons = useCallback(
    (message: ChatMessage) => {
      // R4 / R6 / R8 choices: one button per annotation of the OPTIONS act,
      // e.g. "2. Love — Musiq Soulchild" sends "/select 2" (handled without the LLM).
      const optionsAct = message.dialogue_acts?.find(
        (act) => act.intent === "OPTIONS"
      );
      if (optionsAct && optionsAct.annotations && optionsAct.annotations.length > 0) {
        setChatButtons(
          optionsAct.annotations.map((annotation, index) => {
            const command = "/select " + (index + 1);
            return (
              <QuickReplyButton
                key={index}
                text={annotation.value}
                message={command}
                click={(selected: string) => handleOptionClick(annotation.value, selected)}
              />
            );
          })
        );
        return;
      }

      const buttons = message.attachments?.find(
        (attachment) => attachment.type === "buttons"
      )?.payload.buttons;
      if (!!buttons && buttons.length > 0) {
        setChatButtons(
          buttons.map((button, index) => {
            return (
              <QuickReplyButton
                key={index}
                text={button.title}
                message={button.payload}
                click={handleQuickReply}
              />
            );
          })
        );
      } else {
        setChatButtons([]);
      }
    },
    [handleQuickReply, handleOptionClick]
  );

  useEffect(() => {
    onMessage((message: ChatMessage) => {
      setRawMessages((prev) => [...prev, message]);
      handelMessage(message);
      handleButtons(message);
    });
  }, [onMessage, handleButtons, handelMessage]);

  useEffect(() => {
    onRestart(() => {
      setChatMessages([]);
      setChatButtons([]);
      setRawMessages([]);
    });
  }, [onRestart]);

  return (
    <div className="chat-layout">
      <div className="chat-widget-content chat-main">
        <MDBCard
          id="chatBox"
          className="chat-widget-card"
          style={{ borderRadius: "15px" }}
        >
          <MDBCardHeader
            className="d-flex justify-content-between align-items-center p-3 bg-info text-white border-bottom-0"
            style={{
              borderTopLeftRadius: "15px",
              borderTopRightRadius: "15px",
            }}
          >
            <p className="mb-0 fw-bold">{config.name}</p>
            <p className="mb-0 fw-bold">{user?.username}</p>
          </MDBCardHeader>

          <MDBCardBody>
            <div className="card-body-messages">
              {chatMessages}
              <div className="d-flex flex-wrap justify-content-between">
                {chatButtons}
              </div>
            </div>
          </MDBCardBody>
          <MDBCardFooter className="text-muted d-flex justify-content-start align-items-center p-2">
            <form className="d-flex flex-grow-1" onSubmit={handleInput}>
              <input
                type="text"
                className="form-control form-control-lg"
                id="ChatInput"
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Type message"
                ref={inputRef}
              ></input>
              <button type="submit" className="btn btn-link text-muted">
                <MDBIcon fas size="2x" icon="paper-plane" />
              </button>
            </form>
          </MDBCardFooter>
        </MDBCard>
      </div>

      <PlaylistPanel
        messages={rawMessages}
        onSendMessage={handleSendMessageString}
      />
    </div>
  );
}