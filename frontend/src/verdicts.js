// Every verdict has a word (and a sign on charts) as well as a colour: status is never colour alone.
// word: inline text; tone: its text colour; fill: the solid swatch / bar colour.
export const VERDICT = {
  lags: { label: "Behind the market", word: "behind", tone: "text-danger", fill: "bg-danger" },
  leads: { label: "Ahead of the market", word: "ahead", tone: "text-success", fill: "bg-success" },
  in_line: { label: "In line with the market", word: "in line", tone: "text-muted", fill: "bg-line" },
  too_few: { label: "Too few mentions to tell", word: "too few mentions", tone: "text-muted", fill: "bg-hatch" },
}
