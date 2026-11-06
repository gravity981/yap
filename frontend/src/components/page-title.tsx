/** Title of a main page with a short description of what the page is about. */
export function PageTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="grid gap-1">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
