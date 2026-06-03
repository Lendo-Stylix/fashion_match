# General Crawler Guide

This directory contains the universal guidelines, methodologies, and architectural decisions for the E-Commerce Scraper V3.

## Documents

*   **01_ARCHITECTURE_OVERVIEW.md**: The foundational architecture document. Details the 2-phase philosophy (Discovery vs Harvest).
*   **02_CHROME_CDP_SETUP.md**: Guide on setting up and interacting with the Chrome DevTools Protocol.
*   **03_AX_TREE_DEEP_DIVE.md**: In-depth explanation of the Accessibility Tree, how to compress it, and why it's superior to CSS selectors.
*   **04_DISCOVERY_PHASE.md**: Step-by-step walkthrough of the discovery phase (collecting product URLs).
*   **05_HARVEST_PHASE.md**: Step-by-step walkthrough of the harvest phase (bulk downloading and parsing data).
*   **06_DATA_EXTRACTION_PATTERNS.md**: Universal patterns for extracting data (Embedded JS, JSON-LD, AX Tree static text, API endpoints).
*   **07_ANTI_BLOCKING_AND_RESILIENCE.md**: Strategies for avoiding rate limits, bot detection, and handling popups.
*   **08_CODING_PATTERNS_AND_UTILS.md**: Reusable Python asynchronous coding patterns for CDP interaction, logging, and error handling.
*   **09_STEP_BY_STEP_NEW_WEBSITE.md**: The complete playbook for integrating a brand-new target website into this scraper framework.
