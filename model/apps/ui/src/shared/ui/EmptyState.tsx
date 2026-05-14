import styles from "./EmptyState.module.css";

type EmptyStateProps = {
  title: string;
  description: string;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <section className={styles.card}>
      <h3>{title}</h3>
      <p>{description}</p>
    </section>
  );
}
