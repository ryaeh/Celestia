type PlaceholderProps = {
  title: string;
  blurb: string;
};

export default function Placeholder({ title, blurb }: PlaceholderProps) {
  return (
    <div className="panel">
      <span className="badge">Soon</span>
      <h1>{title}</h1>
      <p className="lead">{blurb}</p>
    </div>
  );
}
