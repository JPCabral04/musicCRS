import { MDBIcon } from "mdb-react-ui-kit";
import Feedback from "./Feedback";
import { ChatMessageDialogueAct } from "../types";

interface TrackMedia {
  id: string;
  name: string;
  artist: string;
  cover?: string | null;
  preview?: string | null;
}

function UserChatMessage({ message }: { message: string }): JSX.Element {
  return (
    <div className="d-flex flex-row justify-content-end mb-4">
      <div
        className="p-3 ms-3 border"
        style={{ borderRadius: "15px", backgroundColor: "#fbfbfb" }}
      >
        <p className="small mb-0">{message}</p>
      </div>
      <img
        src="https://mdbcdn.b-cdn.net/img/Photos/new-templates/bootstrap-chat/ava2-bg.webp"
        alt="User"
        style={{ width: "45px", height: "100%" }}
      />
    </div>
  );
}

function AgentChatMessage({
  message,
  image_url,
  feedback,
  dialogue_acts,
}: {
  message: string;
  image_url?: string;
  feedback: ((message: string, event: string) => void) | null;
  dialogue_acts?: ChatMessageDialogueAct[];
}): JSX.Element {
  // The MEDIA act (sent with every list of options): one card per song with a cover
  // or a preview. Each annotation value is JSON text:
  // {"id": "...", "name": "Numb", "artist": "Linkin Park", "cover": "https://...", "preview": "https://..."}
  const mediaTracks: TrackMedia[] = [];
  const mediaAct = dialogue_acts?.find((act) => act.intent === "MEDIA");
  if (mediaAct && mediaAct.annotations) {
    for (const annotation of mediaAct.annotations) {
      const track: TrackMedia = JSON.parse(annotation.value);
      if (track.cover || track.preview) {
        mediaTracks.push(track);
      }
    }
  }

  return (
    <div className="d-flex flex-row justify-content-start mb-4">
      <div className="text-center">
        <MDBIcon fas size="2x" className="text-muted" icon="robot" />
        {feedback && <Feedback message={message} on_feedback={feedback} />}
      </div>
      <div
        className="p-3 ms-3"
        style={{
          borderRadius: "15px",
          backgroundColor: "rgba(57, 192, 237,.2)",
          maxWidth: "80%",
        }}
      >
        {!!image_url && (
          <div className="d-flex flex-row justify-content-center mb-2">
            <img
              src={image_url}
              alt=""
              style={{ width: "200px", height: "100%", borderRadius: "8px" }}
            />
          </div>
        )}
        <p
          className="small mb-0"
          dangerouslySetInnerHTML={{
            __html: message,
          }}
        ></p>

        {/* Deezer Cover & Audio Preview Cards (T4) */}
        {mediaTracks.length > 0 && (
          <div className="mt-3 pt-2 border-top border-secondary-subtle">
            {mediaTracks.map((track, idx) => (
              <div
                key={`${track.id}-${idx}`}
                className="d-flex align-items-center p-2 my-2 bg-white rounded shadow-sm"
                style={{ gap: "10px" }}
              >
                {track.cover ? (
                  <img
                    src={track.cover}
                    alt={track.name}
                    style={{ width: "50px", height: "50px", borderRadius: "6px", objectFit: "cover" }}
                  />
                ) : (
                  <div
                    className="d-flex align-items-center justify-content-center bg-light text-muted"
                    style={{ width: "50px", height: "50px", borderRadius: "6px", fontSize: "12px" }}
                  >
                    🎵
                  </div>
                )}
                <div className="flex-grow-1 min-vw-0" style={{ overflow: "hidden" }}>
                  <div className="fw-bold small text-truncate">{track.name}</div>
                  <div className="text-muted small text-truncate" style={{ fontSize: "11px" }}>
                    {track.artist}
                  </div>
                  {track.preview ? (
                    <audio controls preload="none" className="mt-1 w-100" style={{ height: "28px" }}>
                      <source src={track.preview} type="audio/mpeg" />
                    </audio>
                  ) : (
                    <span className="text-muted fst-italic" style={{ fontSize: "10px" }}>
                      No preview available
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export { UserChatMessage, AgentChatMessage };