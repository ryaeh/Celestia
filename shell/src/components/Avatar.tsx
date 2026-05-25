type AvatarProps = {
  name: string;
  size?: "xs" | "sm" | "md" | "lg";
};

export default function Avatar({ name, size = "md" }: AvatarProps) {
  return (
    <div className={`avatar avatar-${size}`} aria-hidden>
      {name.trim().charAt(0).toUpperCase() || "C"}
    </div>
  );
}
