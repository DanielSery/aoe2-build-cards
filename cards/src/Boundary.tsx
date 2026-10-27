import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

const KEY = "aoe2-build-cards/v1";

/**
 * A card is drawn rather than validated, so anything the renderer cannot read
 * takes the whole app down and the page goes white — with the library still
 * in local storage and no way to reach it. This turns that into a message and
 * a way out that keeps the cards.
 */
export class Boundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("the editor could not draw this card", error, info);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const rescue = () => {
      const raw = localStorage.getItem(KEY) ?? "{}";
      const url = URL.createObjectURL(new Blob([raw], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "aoe2_build_cards_rescue.json";
      link.click();
      URL.revokeObjectURL(url);
    };

    return (
      <div className="crash">
        <h1>The editor could not draw this card.</h1>
        <p className="hint">{String(error.message || error)}</p>
        <div className="row" style={{ marginTop: 14 }}>
          <button onClick={rescue}>Download my cards</button>
          <button className="danger" onClick={() => { localStorage.removeItem(KEY); location.reload(); }}>
            Clear the library and start again
          </button>
        </div>
        <p className="hint" style={{ marginTop: 14 }}>
          Download first — clearing removes every card saved in this browser,
          and there is no copy anywhere else.
        </p>
      </div>
    );
  }
}
