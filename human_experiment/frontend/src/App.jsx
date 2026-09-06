import { useEffect, useState } from "react";
import {
  Archive,
  Inbox,
  Mail,
  Menu,
  MoreVertical,
  Search,
  ShieldAlert,
  ShieldCheck,
  Star,
} from "lucide-react";

function App() {
  const [email, setEmail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDecision, setSelectedDecision] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [openedAt, setOpenedAt] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  /*
   * For now these come from the URL:
   *
   * http://localhost:5173/?participant=P01&trial=T01
   *
   * Later the participant will receive this exact link.
   */

  const params = new URLSearchParams(window.location.search);

  const participantId =
    params.get("participant") || "P01";

  const trialId =
    params.get("trial") || "T01";


  useEffect(() => {
    loadEmail();
  }, []);


  async function loadEmail() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `http://127.0.0.1:8000/api/email?participant_id=${encodeURIComponent(
          participantId
        )}&trial_id=${encodeURIComponent(trialId)}`
      );

      if (!response.ok) {
        throw new Error("Failed to fetch email");
      }

      const data = await response.json();

      setEmail(data);
      setOpenedAt(data.opened_at);
      setSubmitted(Boolean(data.submitted));
    } catch (err) {
      console.error(err);
      setError("Couldn't load this email.");
    } finally {
      setLoading(false);
    }
  }


  async function handleDecision(decision) {
  if (submitted || submitting || !openedAt) {
    return;
  }

  setSelectedDecision(decision);
  setSubmitting(true);

  try {
    const answeredAt = new Date().toISOString();

    const response = await fetch(
      "http://127.0.0.1:8000/api/response",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          participant_id: participantId,
          trial_id: trialId,
          decision,
          opened_at: openedAt,
          answered_at: answeredAt,
        }),
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Failed to record response");
    }

    setSubmitted(true);
  } catch (err) {
    console.error(err);
    setSelectedDecision(null);
    setError(err.message || "Couldn't record your response.");
  } finally {
    setSubmitting(false);
  }
}


  if (loading) {
    return (
      <div className="app-shell loading-screen">
        <div className="loading-card">
          <div className="loading-spinner" />
          <p>Loading email...</p>
        </div>
      </div>
    );
  }


  if (error) {
    return (
      <div className="app-shell loading-screen">
        <div className="loading-card error-card">
          <ShieldAlert size={42} />

          <h2>Couldn't load the email</h2>

          <p>{error}</p>
        </div>
      </div>
    );
  }


  return (
    <div className="app-shell">

      {/* TOP BAR */}

      <header className="topbar">

        <div className="topbar-left">

          <button className="icon-button">
            <Menu size={22} />
          </button>

          <div className="brand">

            <div className="brand-icon">
              <Mail size={22} />
            </div>

            <span>Mail</span>

          </div>

        </div>


        <div className="search-bar">

          <Search size={20} />

          <span>Search mail</span>

        </div>


        <div className="topbar-right">

          <div className="profile-avatar">
            P
          </div>

        </div>

      </header>


      <div className="main-layout">

        {/* SIDEBAR */}

        <aside className="sidebar">

          <div className="experiment-label">

            <ShieldCheck size={18} />

            <span>Security Experiment</span>

          </div>


          <nav className="sidebar-nav">

            <div className="sidebar-item active">

              <Inbox size={20} />

              <span>Inbox</span>

              <span className="inbox-count">
                1
              </span>

            </div>


            <div className="sidebar-item">

              <Star size={20} />

              <span>Starred</span>

            </div>

          </nav>


          <div className="sidebar-divider" />


          <div className="experiment-note">

            <p>
              Review the email carefully.
            </p>

            <span>
              Then classify it below.
            </span>

          </div>

        </aside>


        {/* MAIN */}

        <main className="content">

          <div className="mail-toolbar">

            <div className="toolbar-left">

              <button className="toolbar-button">
                <Archive size={19} />
              </button>

              <button className="toolbar-button">
                <ShieldAlert size={19} />
              </button>

              <button className="toolbar-button">
                <MoreVertical size={19} />
              </button>

            </div>

          </div>


          <section className="email-container">

            <div className="email-card">

              {/* EMAIL HEADER */}

              <div className="email-header">

                <div className="subject-row">

                  <h1>
                    {email.subject || "(No subject)"}
                  </h1>

                  <button className="star-email">
                    <Star size={20} />
                  </button>

                </div>


                <div className="sender-row">

                  <div className="sender-avatar">

                    {getSenderInitial(
                      email.sender
                    )}

                  </div>


                  <div className="sender-details">

                    <div className="sender-line">

                      <span className="sender-name">
                        {getSenderName(
                          email.sender
                        )}
                      </span>

                      <span className="sender-email">
                        {getSenderEmail(
                          email.sender
                        )}
                      </span>

                    </div>


                    <div className="recipient-line">
                      to me
                    </div>

                  </div>

                </div>

              </div>


              {/* EMAIL BODY */}

              <div className="email-body">
                {email.body}
              </div>

            </div>


            {/* CLASSIFICATION */}

            {!submitted ? (

              <div className="classification-panel">

                <div className="classification-header">

                  <div>

                    <h2>
                      What do you think?
                    </h2>

                    <p>
                      Is this email benign or phishing?
                    </p>

                  </div>

                </div>


                <div className="decision-buttons">

                  <button
                    className={`decision-button benign ${
                      selectedDecision === "benign"
                        ? "selected"
                        : ""
                    }`}
                    onClick={() =>
                      handleDecision("benign")
                    }
                  >

                    <ShieldCheck size={22} />

                    <div>

                      <strong>
                        Benign
                      </strong>

                      <span>
                        Looks safe
                      </span>

                    </div>

                  </button>


                  <button
                    className={`decision-button phishing ${
                      selectedDecision === "phishing"
                        ? "selected"
                        : ""
                    }`}
                    onClick={() =>
                      handleDecision("phishing")
                    }
                  >

                    <ShieldAlert size={22} />

                    <div>

                      <strong>
                        Phishing
                      </strong>

                      <span>
                        Looks suspicious
                      </span>

                    </div>

                  </button>

                </div>

              </div>

            ) : (

              <div className="response-recorded">

                <div className="recorded-icon">
                  <ShieldCheck size={23} />
                </div>

                <div>

                  <strong>
                    Response recorded
                  </strong>

                  <span>
                    Thank you for participating.
                  </span>

                </div>

              </div>

            )}

          </section>

        </main>

      </div>

    </div>
  );
}


/* =========================================================
   EMAIL HELPERS
========================================================= */

function getSenderInitial(sender) {

  if (!sender) {
    return "?";
  }

  return getSenderName(sender)
    .charAt(0)
    .toUpperCase();
}


function getSenderName(sender) {

  if (!sender) {
    return "Unknown sender";
  }

  const match =
    sender.match(/^"?([^"<]+)"?\s*</);

  if (match) {
    return match[1].trim();
  }

  if (sender.includes("@")) {
    return sender.split("@")[0];
  }

  return sender;
}


function getSenderEmail(sender) {

  if (!sender) {
    return "";
  }

  const match =
    sender.match(/<([^>]+)>/);

  if (match) {
    return `<${match[1]}>`;
  }

  return "";
}


export default App;