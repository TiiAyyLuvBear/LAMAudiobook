# 📘 Agentic Audiobook Pipeline -- Full Instructions

## 🎯 Objective

Refactor the project into a modular **Agentic AI system** for audiobook
generation.

------------------------------------------------------------------------

## 🧠 Core Principles

-   Agents ≠ API
-   Organize by capability
-   Centralized workflow orchestration
-   Each agent has `.run()` with clear I/O

------------------------------------------------------------------------

## 🏗️ Target Structure

    project_root/
    ├── src/
    │   ├── api/
    │   ├── agents/
    │   ├── workflows/
    │   ├── services/
    │   ├── utils/
    │   └── main.py
    ├── models/
    ├── data/
    ├── configs/
    ├── tests/
    └── instructions.md

------------------------------------------------------------------------

## 🤖 Agents

### Planner Agent

-   Decide OCR, speaker mode, emotion level

### Document Agents

-   Parser: extract text blocks
-   Cleaner: remove headers/footers
-   Chapter detector: split chapters

### Understanding Agents

-   Narrative: narration vs dialogue
-   Dialogue: speaker + emotion

### Audio Agents

-   Voice planner
-   TTS generator
-   Post-processing

### QC Agent

-   Validate audio vs text

### Memory Agent

-   Maintain speaker voice consistency

------------------------------------------------------------------------

## 🔁 Workflow

Pipeline: Planner → Parser → Cleaner → Chapter → Narrative → Dialogue →
Voice → TTS → QC → Retry → Post-process

Rules: - Only workflow calls agents - Agents never call each other

------------------------------------------------------------------------

## 🌐 API Rules

-   Only accept request
-   No business logic
-   No TTS calls

------------------------------------------------------------------------

## ⚙️ Services

-   Storage
-   Queue
-   Logging

------------------------------------------------------------------------

## 🚫 Strict Rules

-   No monolithic scripts
-   No agent coupling
-   No API logic

------------------------------------------------------------------------

## 🧪 Success Criteria

-   End-to-end pipeline works
-   Agents are modular
-   Easy to swap models

------------------------------------------------------------------------

## 🔍 Checklist

-   No large script
-   No agent-to-agent calls
-   Workflow exists
-   TTS in correct module

------------------------------------------------------------------------

## 🚀 Optional

-   Logging
-   Retry
-   Parallel processing

------------------------------------------------------------------------

# END
