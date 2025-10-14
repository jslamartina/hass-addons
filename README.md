# Documentation Index

Welcome to the CyncLAN Bridge documentation! This guide helps you find the right documentation for your needs.

## 📁 Documentation Structure

```
docs/
├── user/              # User-facing documentation
│   ├── dns-setup.md
│   ├── troubleshooting.md
│   ├── tips.md
│   ├── known-devices.md
│   ├── cloud-relay.md
│   └── assets/
├── developer/         # Developer & AI agent documentation
│   ├── cli-reference.md
│   ├── cloud-relay-implementation.md
│   ├── entity-management.md
│   ├── exploration-notes.md
│   ├── limitations-lifted.md
│   └── test-results.md
├── protocol/          # Protocol research & reverse engineering
│   ├── findings.md
│   ├── packet_structure.md
│   ├── debugging_sessions/
│   ├── mitm-testing.md
│   ├── mode-change-analysis.md
│   └── cleanup-summary.md
└── archive/          # Historical documentation
```

---

## 🚀 Quick Start

### For Users
1. **[Installation Guide](../README.md)** - Add repository to Home Assistant
2. **[DNS Setup](user/dns-setup.md)** - **Required** for local control
3. **[Add-on Quick Start](../cync-lan/README.md)** - First run steps
4. **[Troubleshooting](user/troubleshooting.md)** - Common issues

### For Developers & AI Agents
1. **[Developer Guide](AGENTS.md)** - **START HERE** - Comprehensive development guide
2. **[Testing Tools](../scripts/README.md)** - Automated testing and configuration
3. **[Entity Management](developer/entity-management.md)** - Entity deletion workflows

### For Protocol Researchers
1. **[Protocol Findings](protocol/findings.md)** - Cync protocol reverse engineering
2. **[MITM Testing Guide](protocol/mitm-testing.md)** - Packet capture and analysis

---

## 📚 Documentation by Category

### User Documentation (`docs/user/`)

| Document                                          | Description                                         |
| ------------------------------------------------- | --------------------------------------------------- |
| **[dns-setup.md](user/dns-setup.md)**             | DNS redirection setup (required for add-on to work) |
| **[troubleshooting.md](user/troubleshooting.md)** | Common issues and solutions                         |
| **[tips.md](user/tips.md)**                       | Tips for better experience                          |
| **[known-devices.md](user/known-devices.md)**     | List of supported/tested devices                    |
| **[cloud-relay.md](user/cloud-relay.md)**         | Cloud relay mode documentation                      |

### Developer Documentation (`docs/developer/`)

| Document                                                                     | Description                                   |
| ---------------------------------------------------------------------------- | --------------------------------------------- |
| **[cli-reference.md](developer/cli-reference.md)**                           | CLI command reference for cync-lan package    |
| **[cloud-relay-implementation.md](developer/cloud-relay-implementation.md)** | Cloud relay mode implementation details       |
| **[entity-management.md](developer/entity-management.md)**                   | Guide for managing MQTT entities              |
| **[exploration-notes.md](developer/exploration-notes.md)**                   | UI navigation and system state reference      |
| **[limitations-lifted.md](developer/limitations-lifted.md)**                 | Documentation of resolved testing limitations |
| **[test-results.md](developer/test-results.md)**                             | Comprehensive test execution results          |

### Protocol Research (`docs/protocol/`)

| Document                                                        | Description                             |
| --------------------------------------------------------------- | --------------------------------------- |
| **[findings.md](protocol/findings.md)**                         | Cync protocol reverse engineering notes |
| **[packet_structure.md](protocol/packet_structure.md)**         | Complete protocol packet structures     |
| **[debugging_sessions/](protocol/debugging_sessions/)**         | Protocol debugging session notes        |
| **[mitm-testing.md](protocol/mitm-testing.md)**                 | MITM testing procedures and tools       |
| **[mode-change-analysis.md](protocol/mode-change-analysis.md)** | Analysis of switch mode changes         |
| **[cleanup-summary.md](protocol/cleanup-summary.md)**           | MITM code cleanup notes                 |

### Archive (`docs/archive/`)

Historical documentation and completed testing artifacts.

| Document                                                                                                                       | Description                                                    |
| ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------- |
| **[2025-10-14T18-40-00-absorb-cync-lan-repo-plan.md](archive/2025-10-14T18-40-00-absorb-cync-lan-repo-plan.md)**               | Plan: Consolidate cync-lan repo into hass-addons (✅ completed) |
| **[2025-10-14T18-40-01-remove-symlink-architecture-plan.md](archive/2025-10-14T18-40-01-remove-symlink-architecture-plan.md)** | Plan: Remove symlink to fix semantic search (✅ completed)      |
| **[2025-10-14T16-13-43-cleanup-unused-scripts-plan.md](archive/2025-10-14T16-13-43-cleanup-unused-scripts-plan.md)**           | Plan: Cleanup unused scripts                                   |
| **[2025-10-14T15-39-00-cleanup-summary.md](archive/2025-10-14T15-39-00-cleanup-summary.md)**                                   | Documentation cleanup (October 2025)                           |
| **[2025-10-14T16-00-00-gui-validation-results.md](archive/2025-10-14T16-00-00-gui-validation-results.md)**                     | GUI validation test results                                    |
| **[2025-10-13T14-00-00-refresh-solution.md](archive/2025-10-13T14-00-00-refresh-solution.md)**                                 | Manual refresh button implementation                           |
| **[2025-10-13T15-00-00-throttling-solution.md](archive/2025-10-13T15-00-00-throttling-solution.md)**                           | Command throttling solution                                    |
| **[2025-10-13T13-00-00-gui-validation-phase.md](archive/2025-10-13T13-00-00-gui-validation-phase.md)**                         | Phase 8 GUI testing plan                                       |
| **[2025-10-11T10-00-00-cloud-relay-testing-plan.md](archive/2025-10-11T10-00-00-cloud-relay-testing-plan.md)**                 | Complete cloud relay testing plan (8/8 phases completed)       |
| **[2025-10-08T14-00-00-baseline-review.md](archive/2025-10-08T14-00-00-baseline-review.md)**                                   | Historical code review (October 2025)                          |
| **[2025-10-08T15-00-00-pr-comments.md](archive/2025-10-08T15-00-00-pr-comments.md)**                                           | Historical PR review comments                                  |

### Additional Resources

| Location                                                     | Description                               |
| ------------------------------------------------------------ | ----------------------------------------- |
| **[../scripts/README.md](../scripts/README.md)**             | Automated testing and configuration tools |
| **[../cync-lan/README.md](../cync-lan/README.md)**           | Add-on quick start guide                  |
| **[../cync-lan/CHANGELOG.md](../cync-lan/CHANGELOG.md)**     | Version history and breaking changes      |
| **[../.devcontainer/README.md](../.devcontainer/README.md)** | Devcontainer setup and quirks             |

---

## 🎯 Find What You Need

### "I want to install the add-on"
→ [../README.md](../README.md) + [user/dns-setup.md](user/dns-setup.md) + [../cync-lan/README.md](../cync-lan/README.md)

### "I'm developing the add-on"
→ [AGENTS.md](AGENTS.md) - **Complete development guide**

### "I need to configure cloud relay mode"
→ [../scripts/README.md](../scripts/README.md) (automated tools) or [user/cloud-relay.md](user/cloud-relay.md) (manual)

### "I need to test my changes"
→ [../scripts/test-cloud-relay.sh](../scripts/test-cloud-relay.sh)

### "My devices aren't connecting"
→ [user/dns-setup.md](user/dns-setup.md) + [user/troubleshooting.md](user/troubleshooting.md)

### "I want to understand the protocol"
→ [protocol/findings.md](protocol/findings.md)

### "I need to clean up MQTT entities"
→ [developer/entity-management.md](developer/entity-management.md)

### "I'm using AI agents to work on this project"
→ [AGENTS.md](AGENTS.md) - **Mandatory first read!**

---

## 🤖 For AI Agents

**Always read [AGENTS.md](AGENTS.md) first!**

It contains:
- ✅ Mandatory pre-task checklist
- ✅ Repository structure
- ✅ Development workflows (rebuild vs restart)
- ✅ Testing procedures
- ✅ Known issues and solutions
- ✅ Coding conventions
- ✅ Critical DO and DON'T rules

**Quick commands:**
```bash
ha addons logs local_cync-lan     # View logs
./scripts/configure-addon.sh      # Configure addon
ha addons restart local_cync-lan  # Restart addon
ha addons rebuild local_cync-lan  # Rebuild after Python changes
```

---

## 📝 Documentation Principles

1. **Single Source of Truth** - Each topic documented once
2. **Clear Hierarchy** - User, developer, and protocol docs separated
3. **Cross-Reference** - Link instead of duplicate
4. **Keep Current** - Remove stale artifacts
5. **Easy Navigation** - Clear paths to information

---

## 🔍 Search Tips

### By Role
- **User**: Start with `docs/user/`
- **Developer**: Start with `docs/developer/agents-guide.md`
- **Protocol Researcher**: Start with `docs/protocol/`

### By Task
- **Installation**: `../README.md` and `docs/user/dns-setup.md`
- **Troubleshooting**: `docs/user/troubleshooting.md`
- **Development**: `docs/developer/agents-guide.md`
- **Testing**: `../scripts/README.md`
- **Protocol Analysis**: `docs/protocol/findings.md`

### By File Type
- **Markdown docs**: This folder (`docs/`)
- **Shell scripts**: `../scripts/`
- **Add-on files**: `../cync-lan/`
- **MITM tools**: `../mitm/` (with docs in `docs/protocol/`)

---

## 📊 Documentation Maintenance

### Last Major Reorganization
**Date:** October 14, 2025

**Changes:**
- ✅ Moved all documentation to `/docs` folder
- ✅ Created clear hierarchy: user/developer/protocol
- ✅ Removed 11 redundant files (~2,000 lines)
- ✅ Updated all cross-references
- ✅ Created this navigation index

**Result:**
- Organized: Clear structure
- Consolidated: No redundancy
- Current: All references valid
- Maintainable: Easy to update

See [archive/cleanup-summary.md](archive/cleanup-summary.md) for details.

---

## 💡 Contributing to Documentation

When adding or updating documentation:

1. **Choose the right category:**
   - User-facing? → `docs/user/`
   - Developer guide? → `docs/developer/`
   - Protocol research? → `docs/protocol/`

2. **Update this index** (docs/README.md)

3. **Update cross-references** in affected files

4. **Follow naming conventions:**
   - Use kebab-case for filenames
   - Be descriptive but concise
   - Add to appropriate subfolder

5. **Test all links** before committing

---

## 🆘 Need Help?

- **For usage questions**: See [user/troubleshooting.md](user/troubleshooting.md)
- **For development questions**: See [AGENTS.md](AGENTS.md)
- **For protocol questions**: See [protocol/findings.md](protocol/findings.md)
- **Can't find something?**: Check this index or search the repository

---

*Last Updated: October 14, 2025*
*Documentation organized and maintained by: Repository contributors*
*For the latest updates, always refer to the repository*
