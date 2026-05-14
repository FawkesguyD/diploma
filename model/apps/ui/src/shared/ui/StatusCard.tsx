import styles from "./StatusCard.module.css";

type StatusCardProps = {
  title: string;
  description: string;
  tone?: "default" | "error";
  actionLabel?: string;
  onAction?: () => void;
};

export function StatusCard({
  title,
  description,
  tone = "default",
  actionLabel,
  onAction,
}: StatusCardProps) {
  return (
    <section className={`${styles.card} ${tone === "error" ? styles.error : ""}`}>
      <h2>{title}</h2>
      <p>{description}</p>
      {actionLabel && onAction ? (
        <button className={styles.actionButton} onClick={onAction} type="button">
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}
