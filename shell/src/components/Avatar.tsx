type AvatarProps = {
  name: string;
  size?: "sm" | "md" | "lg";
};

const SIZE = {
  sm: 40,
  md: 72,
  lg: 120,
} as const;

export default function Avatar({ name, size = "md" }: AvatarProps) {
  const px = SIZE[size];

  return (
    <div
      className={`avatar avatar-${size}`}
      style={{ width: px, height: px }}
      aria-hidden
    >
      <span>{name.trim().charAt(0).toUpperCase() || "C"}</span>
    </div>
  );
}
