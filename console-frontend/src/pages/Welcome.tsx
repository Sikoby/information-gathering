import { useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Separator,
} from "@ig/ui";

export function Welcome() {
  const navigate = useNavigate();
  const buttonRef = useRef<HTMLButtonElement>(null);

  const dismiss = useCallback(() => {
    sessionStorage.setItem("welcome:dismissed", "1");
    navigate("/", { replace: true });
  }, [navigate]);

  useEffect(() => {
    const prev = document.title;
    document.title = "Welcome · meeting console";
    return () => {
      document.title = prev;
    };
  }, []);

  useEffect(() => {
    buttonRef.current?.focus();
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-12 space-y-12">
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={dismiss}>
          Skip
        </Button>
      </div>

      <section>
        <h1 className="text-3xl font-semibold tracking-tight">
          Welcome to the meeting console
        </h1>
        <p className="mt-3 text-muted-foreground">
          An AI agent runs interview-style meetings from a script you generate
          here (a "template"), and you watch the conversation live as it
          happens.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight">
          Three ways to start
        </h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Card role="group" aria-labelledby="start-prompt-title">
            <CardHeader>
              <CardTitle id="start-prompt-title">Start with a prompt</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Describe what the meeting should cover. The agent drafts an
                outline of topics and questions you can edit.
              </CardDescription>
            </CardContent>
          </Card>
          <Card role="group" aria-labelledby="start-pptx-title">
            <CardHeader>
              <CardTitle id="start-pptx-title">
                Start with a PowerPoint
              </CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Upload a .pptx. Each slide becomes a topic and your speaker
                notes become the agent's script.
              </CardDescription>
            </CardContent>
          </Card>
          <Card role="group" aria-labelledby="start-pdf-title">
            <CardHeader>
              <CardTitle id="start-pdf-title">Start with a PDF</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>
                Upload a .pdf. Each page becomes a topic. Useful for briefing
                docs and one-pagers.
              </CardDescription>
            </CardContent>
          </Card>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight">
          Template vs meeting
        </h2>
        <div className="mt-4 grid gap-8 md:grid-cols-2">
          <div>
            <h3 className="text-base font-semibold">Template</h3>
            <p className="mt-2 text-muted-foreground">
              The reusable definition. Generated once, then edited freely. One
              template can spawn many meetings.
            </p>
          </div>
          <div>
            <h3 className="text-base font-semibold">Meeting</h3>
            <p className="mt-2 text-muted-foreground">
              A live, AI-run instance of a template. Goes from running to done.
              Only one runs at a time.
            </p>
          </div>
        </div>
        <Separator className="mt-8" />
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight">How it works</h2>
        <ol className="mt-4 list-decimal pl-6 space-y-2 text-base">
          <li>Create a template — from a prompt, a PowerPoint, or a PDF.</li>
          <li>
            Edit the topics, questions, and speaker notes until it reads right.
          </li>
          <li>
            Start a meeting — the agent joins a video room and runs the script.
            You watch live.
          </li>
        </ol>
      </section>

      <section className="flex justify-center pt-4">
        <Button ref={buttonRef} size="lg" onClick={dismiss}>
          Got it, take me to the dashboard
        </Button>
      </section>
    </div>
  );
}
