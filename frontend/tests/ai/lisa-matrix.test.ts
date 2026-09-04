import { describe, it, expect } from "vitest";
import { answerQuestion } from "../../lib/mock/ai/engine";
import type { AiQuestionContext, AiResponse } from "../../lib/mock/ai/engine";
import { getControlTowerFleet } from "../../lib/mock/ai/analytics";

function log(q: string, r: AiResponse, ctx?: AiQuestionContext) {
  // eslint-disable-next-line no-console
  console.log(
    `\nQ: ${q}${ctx ? ` [ctx=${JSON.stringify(ctx)}]` : ""}\n  headline: ${r.headline}\n  insufficientData: ${!!r.insufficientData}\n  understood: ${r.understood ? JSON.stringify(r.understood) : "none"}\n  narrative: ${JSON.stringify(r.narrative)}`
  );
}

describe("Lisa question matrix", () => {
  it("prints which aircraft is AOG", () => {
    const fleet = getControlTowerFleet();
    console.log("AOG aircraft:", fleet.filter((f) => f.operationalStatus === "AOG").map((f) => f.registration));
  });

  it("runs the matrix without crashing and logs results", () => {
    const questions: { q: string; ctx?: AiQuestionContext }[] = [
      { q: "What's wrong with VT-ABC?" },
      { q: "What maintenance is due for VT-XYZ?" },
      { q: "What should I prioritize?" },
      { q: "Which task should I complete first?" },
      { q: "What is blocking WO-1050?" },
      { q: "Is WO-1054 late?" },
      { q: "What is the TAT status?" },
      { q: "Which tasks may impact TAT?" },
      { q: "What is the critical path to recover VT-XYZ?" },
      { q: "What part is blocking recovery?", ctx: { previousQuestion: "What is the critical path to recover VT-XYZ?" } },
      { q: "Which vendor should we use?" },
      { q: "Which vendor should we use?", ctx: { previousQuestion: "What part is blocking recovery?", recentQuestions: ["What is the critical path to recover VT-XYZ?", "What part is blocking recovery?"] } },
      { q: "Is the evidence accepted?" },
      { q: "What evidence is missing?" },
      { q: "What is the inspection status?" },
      { q: "Is RII required?" },
      { q: "Is the technician authorized?" },
      { q: "What are the release blockers?" },
      { q: "Why can't this aircraft be released?" },
      { q: "Are there any new regulatory updates?" },
      { q: "Does this regulatory update affect VT-ABC?" },
      { q: "What should I do next?" },
      { q: "Give me today's MRO priorities." },
      { q: "What's changed since yesterday?" },
      // ambiguous, no scope
      { q: "Is this late?" },
      // safety-restricted
      { q: "Can this aircraft be released?" },
      { q: "Can we skip inspection?" },
      { q: "Can I bypass the evidence gate?" },
    ];

    for (const { q, ctx } of questions) {
      let r: AiResponse | undefined;
      expect(() => {
        r = answerQuestion(q, ctx);
      }).not.toThrow();
      if (r) log(q, r, ctx);
    }

    // Follow-up chain test
    const r1 = answerQuestion("What's wrong with VT-ABC?");
    log("What's wrong with VT-ABC?", r1);
    const r2 = answerQuestion("What should I fix first?", { previousQuestion: "What's wrong with VT-ABC?", recentQuestions: ["What's wrong with VT-ABC?"] });
    log("What should I fix first?", r2, { previousQuestion: "What's wrong with VT-ABC?" });
    const r3 = answerQuestion("What about the part?", { previousQuestion: "What should I fix first?", recentQuestions: ["What's wrong with VT-ABC?", "What should I fix first?"] });
    log("What about the part?", r3, { previousQuestion: "What should I fix first?" });
    const r4 = answerQuestion("Which vendor should we use?", { previousQuestion: "What about the part?", recentQuestions: ["What's wrong with VT-ABC?", "What should I fix first?", "What about the part?"] });
    log("Which vendor should we use?", r4, { previousQuestion: "What about the part?" });

    expect(true).toBe(true);
  });
});
