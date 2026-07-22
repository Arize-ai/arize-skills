# Changelog

## [1.2.0](https://github.com/Arize-ai/arize-skills/compare/v1.1.0...v1.2.0) (2026-07-22)


### Features

* **arize-span-routing:** add skill for multi-space destination routing ([#105](https://github.com/Arize-ai/arize-skills/issues/105)) ([32685de](https://github.com/Arize-ai/arize-skills/commit/32685de168c6115d416f6ce7734a6b384a157090))


### Bug Fixes

* **arize-evaluator:** correct custom code evaluator import path and evaluate() signature ([#102](https://github.com/Arize-ai/arize-skills/issues/102)) ([e66a84a](https://github.com/Arize-ai/arize-skills/commit/e66a84aabd81bec5e06e3ea55370580daccb42f3))
* **arize-instrumentation:** credential precedence, safe sourcing, onboarding ([#91](https://github.com/Arize-ai/arize-skills/issues/91)) ([92770d3](https://github.com/Arize-ai/arize-skills/commit/92770d32406478e4580b438c55e9399eab219c23))
* **arize-instrumentation:** deterministic verification + post-verify quality checks ([#92](https://github.com/Arize-ai/arize-skills/issues/92)) ([c57a155](https://github.com/Arize-ai/arize-skills/commit/c57a15580ded76028b005b7655ba58b02bfca422))
* **arize-instrumentation:** scope gate, consent, progress signaling, handoff ([#93](https://github.com/Arize-ai/arize-skills/issues/93)) ([b9247c4](https://github.com/Arize-ai/arize-skills/commit/b9247c4193e105cffa7d5b533475cb2167b21602))
* pass awesome-copilot external-plugin quality gates ([#95](https://github.com/Arize-ai/arize-skills/issues/95)) ([232e70b](https://github.com/Arize-ai/arize-skills/commit/232e70ba7aab183733297d0a564111a8effb86a8))
* **skills:** keep secrets out of coding agent chat ([#104](https://github.com/Arize-ai/arize-skills/issues/104)) ([2c9926d](https://github.com/Arize-ai/arize-skills/commit/2c9926dc102a11e05ac706979bf86641ae5e662c))
* **skills:** use ARIZE_SPACE_ID for instrumentation ([#107](https://github.com/Arize-ai/arize-skills/issues/107)) ([fa38c43](https://github.com/Arize-ai/arize-skills/commit/fa38c437a830d7ddfbf69bf93165756938d04bb0))

## [1.1.0](https://github.com/Arize-ai/arize-skills/compare/v1.0.0...v1.1.0) (2026-07-01)


### Features

* add arize-admin skill ([#58](https://github.com/Arize-ai/arize-skills/issues/58)) ([1c23eea](https://github.com/Arize-ai/arize-skills/commit/1c23eeaf3f405496f5fb72e31ab05ac11e7bb08c))
* add arize-ai-provider-integration skill ([#31](https://github.com/Arize-ai/arize-skills/issues/31)) ([7501152](https://github.com/Arize-ai/arize-skills/commit/7501152626229bf2ae40ab9ea6d6bbb8a8989002))
* add arize-annotation skill for configs and span annotations ([#32](https://github.com/Arize-ai/arize-skills/issues/32)) ([8ed111e](https://github.com/Arize-ai/arize-skills/commit/8ed111e0f3d78caa3331cfd5a4145ca2cf302847))
* add arize-compliance-audit skill ([#53](https://github.com/Arize-ai/arize-skills/issues/53)) ([05d1251](https://github.com/Arize-ai/arize-skills/commit/05d1251c88710352a2430832319b26c11458f522))
* add GitHub Copilot as supported agent in installer ([#67](https://github.com/Arize-ai/arize-skills/issues/67)) ([9586490](https://github.com/Arize-ai/arize-skills/commit/95864906d93e08bd1368d8ecf9fc1abd2bca2127))
* **arize-trace:** improve 500-span truncation UX ([#68](https://github.com/Arize-ai/arize-skills/issues/68)) ([817e515](https://github.com/Arize-ai/arize-skills/commit/817e51549fca14d528a29f484fce95c9a3db52d8))
* Composable credential loading from .env files ([#38](https://github.com/Arize-ai/arize-skills/issues/38)) ([071f4bd](https://github.com/Arize-ai/arize-skills/commit/071f4bd1cb5b85eb552f9d4485d605ed78dd35ee))
* Eval Skills  ([#30](https://github.com/Arize-ai/arize-skills/issues/30)) ([49744b9](https://github.com/Arize-ai/arize-skills/commit/49744b94854c242abb63e788ec86d82d975479c6))
* Improve handling of `ax profile` issues ([#33](https://github.com/Arize-ai/arize-skills/issues/33)) ([7a5de88](https://github.com/Arize-ai/arize-skills/commit/7a5de88fe4d76ce867effbfdbff0a9e31f9c3663))
* **instrumentation:** add Go to arize-instrumentation skill ([#55](https://github.com/Arize-ai/arize-skills/issues/55)) ([7b6e10f](https://github.com/Arize-ai/arize-skills/commit/7b6e10f61c87884cba0e2ffff829f9e7535e6d75))
* **skills:** update all skills for ax CLI v0.21.0 ([#65](https://github.com/Arize-ai/arize-skills/issues/65)) ([85829fd](https://github.com/Arize-ai/arize-skills/commit/85829fd042b2aca6af66a6ff973028a69a22f203))
* use ax cli for trace verification on arize-trace skill ([619df6f](https://github.com/Arize-ai/arize-skills/commit/619df6f6adea42806c74931e9687235bf235e354))
* use names instead of IDs throughout skills ([#43](https://github.com/Arize-ai/arize-skills/issues/43)) ([3b843da](https://github.com/Arize-ai/arize-skills/commit/3b843daefded32759992f6979d1417b7bb3d2b74))


### Bug Fixes

* add missing --classification-choices flag and data granularity docs to evaluator skill ([#36](https://github.com/Arize-ai/arize-skills/issues/36)) ([3529f4b](https://github.com/Arize-ai/arize-skills/commit/3529f4b9b57e2923d280c16bf6793ed2f0738694))
* add missing project name and flush rules to arize-instrumentation skill ([#5](https://github.com/Arize-ai/arize-skills/issues/5)) ([2b382c0](https://github.com/Arize-ai/arize-skills/commit/2b382c0ff54aa1052cbf7dddd360c9c3f794a057))
* address dogfooding feedback across experiment and evaluator skills ([#49](https://github.com/Arize-ai/arize-skills/issues/49)) ([9561477](https://github.com/Arize-ai/arize-skills/commit/9561477eb929c59cc6396bb3d6bbcdc688c1482f))
* address real-world workflow feedback for trace and evaluator skills ([#46](https://github.com/Arize-ai/arize-skills/issues/46)) ([6fbc230](https://github.com/Arize-ai/arize-skills/commit/6fbc23061f416931d387ddd29e18409861cc847d))
* **arize-evaluator:** add application-side session.id bridge for multi-turn evals ([#47](https://github.com/Arize-ai/arize-skills/issues/47)) ([0dea755](https://github.com/Arize-ai/arize-skills/commit/0dea7550e08dfbf6bfe417afbbaccd52e4c136fe))
* Change limit shorthand ([7c665be](https://github.com/Arize-ai/arize-skills/commit/7c665be6ca99dffcf2119a54e0a126f0cf215ac7))
* improve ax install instructions with PATH, SSL, and Windows support ([e2a8e2a](https://github.com/Arize-ai/arize-skills/commit/e2a8e2a2f9e907467391633d04970ec691fcb502))
* **instrumentation:** address Go code quality issues in arize-instrumentation skill ([#57](https://github.com/Arize-ai/arize-skills/issues/57)) ([e9112f6](https://github.com/Arize-ai/arize-skills/commit/e9112f67127091301039da6081405e96085c8180))
* **instrumentation:** close Go gaps an agent-driven smoke test surfaced ([#56](https://github.com/Arize-ai/arize-skills/issues/56)) ([6a622b6](https://github.com/Arize-ai/arize-skills/commit/6a622b6c962907f54ca3578cb2cabff161d8aae6))
* **instrumentation:** replace broken API keys URL with ax profiles flow ([#48](https://github.com/Arize-ai/arize-skills/issues/48)) ([40dabb5](https://github.com/Arize-ai/arize-skills/commit/40dabb5f04a2e3a04cdb6e90253fb363d226eb4f))
* **readme:** correct 40+ agents link to vercel-labs/skills ([#66](https://github.com/Arize-ai/arize-skills/issues/66)) ([a06dcf4](https://github.com/Arize-ai/arize-skills/commit/a06dcf4498c6a0c28d55779cc5e015b31a3433ab))
* replace delete with revoke ([#71](https://github.com/Arize-ai/arize-skills/issues/71)) ([1c353e0](https://github.com/Arize-ai/arize-skills/commit/1c353e036c40e31d026dbbff1c09b9dcbbc89e5d))
* update ax traces export --limit docs (500 spans -&gt; 50 traces) ([1c1ba90](https://github.com/Arize-ai/arize-skills/commit/1c1ba90edac32c453fc8d008fe5c0298c3fbd7ed))
* Update dataset and experiment skills for file parameters ([#34](https://github.com/Arize-ai/arize-skills/issues/34)) ([897b402](https://github.com/Arize-ai/arize-skills/commit/897b4022c898a7d6cde33877eeda65c01ec344d3))

## [1.0.0] - 2026-06-08

Initial release.

### Install
```bash
npx skills add Arize-ai/arize-skills
```
