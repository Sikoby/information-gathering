/** The list of invited emails on a scheduled meeting. Renders nothing if empty. */
export function InviteesList({ emails }: { emails: string[] }) {
  if (emails.length === 0) return null;
  return (
    <div>
      <p className="text-sm font-medium">Invitees ({emails.length})</p>
      <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
        {emails.map((email) => (
          <li key={email}>{email}</li>
        ))}
      </ul>
    </div>
  );
}
