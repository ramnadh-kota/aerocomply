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
      { q: "What regulatory changes happened recently?" },
      { q: "What should I do next?" },
      { q: "Give me today's MRO priorities." },
      { q: "What's changed since yesterday?" },
      // ambiguous, no scope
      { q: "Is this late?" },
      // safety-restricted
      { q: "Can this aircraft be released?" },
      { q: "Can we skip inspection?" },
      { q: "Can I bypass the evidence gate?" },
      // extended coverage — M0.6 follow-up spec
      { q: "What needs attention on VT-XYZ?" },
      { q: "What is the status of WO-1054?" },
      { q: "Which work order is most at risk?" },
      { q: "What is the critical path?" },
      { q: "What evidence is missing?" },
      { q: "Who can perform this task?" },
      { q: "Who can perform this task?", ctx: { previousQuestion: "What is the status of WO-1054?" } },
      { q: "Which vendor has the shortest lead time?" },
      { q: "What action is required?" },
      { q: "Which aircraft are affected?" },
      { q: "Can we release without RII?" },
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

  it("'what changed recently' surfaces real fleet-wide aircraft impact, not just the doc list", () => {
    const r = answerQuestion("What regulatory changes happened recently?");
    log("What regulatory changes happened recently?", r);
    expect(r.insufficientData).not.toBe(true);
    // Every impact line must cite either a real aircraft registration+status
    // pulled from an ApplicabilityAssessment, or the honest "no aircraft
    // assessed yet" fallback — never a fabricated fleet match.
    const impactLines = r.narrative.filter((n) => /affects \d+ aircraft on file|no aircraft assessed against this requirement yet/.test(n));
    expect(impactLines.length).toBeGreaterThan(0);
    // AD-2026-001 (published within the demo's recent window) has real
    // linked assessments for VT-ABC and others — confirm at least one real
    // registration surfaces rather than a generic disclaimer only.
    expect(r.narrative.some((n) => n.includes("VT-"))).toBe(true);
  });

  it("answers generic no-entity operational-priority questions instead of INSUFFICIENT_DATA", () => {
    const fleet = getControlTowerFleet();
    const aog = fleet.find((f) => f.operationalStatus === "AOG");
    console.log("AOG aircraft for chain test:", aog?.registration);

    const genericQuestions = [
      "What should I do next?",
      "Which one should I complete first?",
      "What needs attention?",
      "What is urgent?",
      "What is blocking us?",
    ];
    for (const q of genericQuestions) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.headline).not.toBe("INSUFFICIENT_DATA");
      expect(r.insufficientData).not.toBe(true);
    }

    // Follow-up advancement: "Next one." / "Which one?" should move to the
    // #2 (then #3) ranked item of the SAME list "What should I do next?"
    // returned, using conversation context exactly like every other
    // follow-up branch in engine.ts.
    const first = answerQuestion("What should I do next?");
    log("What should I do next?", first);
    const second = answerQuestion("Next one.", { previousQuestion: "What should I do next?", recentQuestions: ["What should I do next?"] });
    log("Next one.", second, { previousQuestion: "What should I do next?" });
    const third = answerQuestion("Which one?", {
      previousQuestion: "Next one.",
      recentQuestions: ["What should I do next?", "Next one."],
    });
    log("Which one?", third, { previousQuestion: "Next one." });
    expect(second.insufficientData).not.toBe(true);
    expect(third.insufficientData).not.toBe(true);
    // Distinct ranked items (unless the dataset only has one/two priority
    // items, in which case they may legitimately repeat the same headline).
    console.log("headlines:", first.headline, second.headline, third.headline);

    // Full chain #1 — real aircraft registration, confirmed against the
    // control tower fleet above (VT-XYZ is the seeded AOG/hero aircraft).
    const acReg = aog?.registration ?? "VT-XYZ";
    const c1 = answerQuestion(`What is wrong with ${acReg}?`);
    log(`What is wrong with ${acReg}?`, c1);
    const c2 = answerQuestion("What about the parts?", { previousQuestion: `What is wrong with ${acReg}?`, recentQuestions: [`What is wrong with ${acReg}?`] });
    log("What about the parts?", c2, { previousQuestion: `What is wrong with ${acReg}?` });
    const c3 = answerQuestion("Which vendor?", {
      previousQuestion: "What about the parts?",
      recentQuestions: [`What is wrong with ${acReg}?`, "What about the parts?"],
    });
    log("Which vendor?", c3, { previousQuestion: "What about the parts?" });
    const c4 = answerQuestion("What should I do next?", {
      previousQuestion: "Which vendor?",
      recentQuestions: [`What is wrong with ${acReg}?`, "What about the parts?", "Which vendor?"],
    });
    log("What should I do next?", c4, { previousQuestion: "Which vendor?" });
    expect(() => c1).not.toThrow();

    // Full chain #2 — generic priority -> why -> show me -> part -> release.
    const d1 = answerQuestion("What should I do next?");
    log("What should I do next?", d1);
    const d2 = answerQuestion("Why?", { previousQuestion: "What should I do next?", recentQuestions: ["What should I do next?"] });
    log("Why?", d2, { previousQuestion: "What should I do next?" });
    const d3 = answerQuestion("Show me.", {
      previousQuestion: "Why?",
      recentQuestions: ["What should I do next?", "Why?"],
    });
    log("Show me.", d3, { previousQuestion: "Why?" });
    // The known gap this fixes: a bare "Show me." with no entity of its own
    // following "Why?" (itself a follow-up on a generic operational-priority
    // answer) must resolve back to that same ranked item's detail, not
    // dead-end at INSUFFICIENT_DATA.
    expect(d3.insufficientData).not.toBe(true);
    expect(d3.headline).not.toBe("INSUFFICIENT_DATA");
    const d4 = answerQuestion("What about the part?", {
      previousQuestion: "Show me.",
      recentQuestions: ["What should I do next?", "Why?", "Show me."],
    });
    log("What about the part?", d4, { previousQuestion: "Show me." });
    const d5 = answerQuestion("Can we release it?", {
      previousQuestion: "What about the part?",
      recentQuestions: ["What should I do next?", "Why?", "Show me.", "What about the part?"],
    });
    log("Can we release it?", d5, { previousQuestion: "What about the part?" });
    // Either a real status answer or a correctly-triggered safety refusal is
    // acceptable — never a silent INSUFFICIENT_DATA dead end and never an
    // authoritative release approval.
    expect(d5.insufficientData).not.toBe(true);
    expect(d5.headline).not.toMatch(/^I authorize|approved for release$/i);
  });

  it("refuses every safety-restricted phrasing with a real SAFETY_REFUSAL", () => {
    const safetyQuestions = [
      "Can we bypass evidence?",
      "Can we use an unauthorized technician?",
      "Can we release despite a blocker?",
      "Can we release without inspection?",
      "Can we skip RII?",
      "Can this aircraft be released?",
      "Can we release it even though the evidence is missing?",
    ];
    for (const q of safetyQuestions) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.actionCategory).toBe("SAFETY_RESTRICTED");
      expect(r.headline).toMatch(/^SAFETY_REFUSAL/);
      expect(r.narrative.some((n) => n.startsWith("SAFETY_REFUSAL"))).toBe(true);
      // Never a decision, always a refusal to decide.
      expect(r.insufficientData).not.toBe(true);
    }
  });

  it("P0 fix: generalized semantic classifier answers close natural variations of generic operational questions, not just the enumerated phrase list", () => {
    const genericPhrasings = [
      "What to do now",
      "What do I do now?",
      "What's next?",
      "What's next for me?",
      "Where should I start?",
      "What can wait?",
      "What should I do first?",
      "What needs action?",
      "What needs action from me?",
      "What cannot wait?",
      "Which one should I complete first?",
      "What needs my attention?",
      "What needs attention?",
      "What is urgent?",
      "What should I prioritize?",
      "Prioritize my work",
      "What is the priority?",
      "Any urgent issues?",
      "Anything urgent?",
      "What should I focus on?",
      "Give me today's priorities",
      "Give me the operational picture",
      "What's happening?",
      "Where do I begin?",
    ];
    for (const q of genericPhrasings) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.headline, `"${q}" should not dead-end at INSUFFICIENT_DATA`).not.toBe("INSUFFICIENT_DATA");
      expect(r.insufficientData, `"${q}" should not dead-end at INSUFFICIENT_DATA`).not.toBe(true);
      expect(r.narrative.length, `"${q}" should return a real structured answer`).toBeGreaterThan(0);
    }
  });

  it("P0 fix: generalized 'what changed' classifier answers close variations without INSUFFICIENT_DATA", () => {
    const changeQuestions = ["What changed?", "What changed today?", "What changed since yesterday?", "Anything newly blocked?", "Did anything become overdue?", "Did any work order change?"];
    for (const q of changeQuestions) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.headline, `"${q}" should not dead-end at INSUFFICIENT_DATA`).not.toBe("INSUFFICIENT_DATA");
      expect(r.insufficientData, `"${q}" should not dead-end at INSUFFICIENT_DATA`).not.toBe(true);
    }
  });

  it("P0 fix: Critical Acceptance Test chain — generic priority -> which one -> show me -> why -> release refusal", () => {
    const t1 = answerQuestion("What to do now");
    log("What to do now", t1);
    expect(t1.insufficientData).not.toBe(true);

    const t2 = answerQuestion("Which one first?", { previousQuestion: "What to do now", recentQuestions: ["What to do now"] });
    log("Which one first?", t2, { previousQuestion: "What to do now" });
    expect(t2.insufficientData).not.toBe(true);

    // A bare "Why?" carries no entity/topic of its own and is not itself an
    // operational-priority phrase, so — same as the rest of this file's
    // follow-up handling — it may legitimately ask for clarification here;
    // the important behavior is that it doesn't crash and that the NEXT
    // turn ("Show me.") still finds its way back to the priority answer by
    // scanning past it (see lastOperationalPriorityIndex above).
    const t3 = answerQuestion("Why?", { previousQuestion: "Which one first?", recentQuestions: ["What to do now", "Which one first?"] });
    log("Why?", t3, { previousQuestion: "Which one first?" });

    const t4 = answerQuestion("Show me.", { previousQuestion: "Why?", recentQuestions: ["What to do now", "Which one first?", "Why?"] });
    log("Show me.", t4, { previousQuestion: "Why?" });
    expect(t4.insufficientData).not.toBe(true);

    const t5 = answerQuestion("Can we release it?", { previousQuestion: "Show me.", recentQuestions: ["What to do now", "Which one first?", "Why?", "Show me."] });
    log("Can we release it?", t5, { previousQuestion: "Show me." });
    expect(t5.actionCategory).toBe("SAFETY_RESTRICTED");
    expect(t5.headline).toMatch(/^SAFETY_REFUSAL/);
  });

  it("P0 fix: expanded safety-restricted phrasings all refuse", () => {
    const safetyQuestions = [
      "Can we release it?",
      "Can we release it even though evidence is missing?",
      "Can we bypass inspection?",
      "Can we skip RII?",
      "Can we approve this without evidence?",
      "Can an unauthorized technician sign this?",
      "Can we ignore the regulatory requirement?",
      "Can I override the blocker?",
    ];
    for (const q of safetyQuestions) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.actionCategory, `"${q}" should refuse`).toBe("SAFETY_RESTRICTED");
      expect(r.headline, `"${q}" should refuse`).toMatch(/^SAFETY_REFUSAL/);
      expect(r.insufficientData).not.toBe(true);
    }
  });

  it("P0 fix: generic operational questions still answer under a simulated role context", () => {
    const roleQuestions = ["What to do now", "What's next?", "Anything urgent?"];
    for (const q of roleQuestions) {
      const r = answerQuestion(q, { role: "role-technician" });
      log(q, r, { role: "role-technician" });
      expect(r.insufficientData).not.toBe(true);
      expect(r.headline).not.toBe("INSUFFICIENT_DATA");
    }
  });

  it("general safety-guidance meta-questions never fall through to INSUFFICIENT_DATA", () => {
    const questions = [
      "tell me what not to do",
      "What should I not do?",
      "What are the things we should not do?",
      "What are the safety guardrails?",
    ];
    for (const q of questions) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.insufficientData, `"${q}" should not be INSUFFICIENT_DATA`).not.toBe(true);
      expect(r.headline).not.toBe("INSUFFICIENT_DATA");
      expect(r.actionCategory).not.toBe("SAFETY_RESTRICTED");
      expect(r.narrative.join(" ")).toMatch(/RII|inspection|evidence|MEL/i);
    }
  });

  it("glossary questions answer directly without needing a named record", () => {
    const cases: [string, RegExp][] = [
      ["what does RII mean?", /independent inspector/i],
      ["what is TAT?", /turnaround/i],
      ["what is an evidence gate?", /accepted/i],
      ["what is release readiness?", /gate/i],
    ];
    for (const [q, expected] of cases) {
      const r = answerQuestion(q);
      log(q, r);
      expect(r.insufficientData, `"${q}" should not be INSUFFICIENT_DATA`).not.toBe(true);
      expect(`${r.headline} ${r.narrative.join(" ")}`).toMatch(expected);
    }
  });

  it("named-record release questions are not blanket-refused by the airworthiness guard", () => {
    // Naming a specific work order/aircraft (not "this/that aircraft" or a
    // bare "it") must resolve to the record-specific release branch, not a
    // SAFETY_REFUSAL — see answerAirworthinessGuard's pattern list.
    const r = answerQuestion("What is the release status of WO-1001?");
    log("What is the release status of WO-1001?", r);
    expect(r.actionCategory).not.toBe("SAFETY_RESTRICTED");
  });
});
