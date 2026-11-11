# Cowork Cookbook

Recipes, plugins and pictures that help people put Copilot Cowork to work on the work they already do.

The customer plugin in this repository is **Launchpad for Cowork**. It finds work Cowork can take off your plate, shows what the result looks like, builds it on your own files, tests it on a period you know and keeps it as a skill.

Status: preview. The repository sits on a personal account for now and may move to a Microsoft organisation. [Add the agreed support statement before sharing with customers.]

## What is in this repository

| Location | What it holds |
|---|---|
| `docs/` | Pictures that Launchpad's cards show (`docs/assets/`), and a gallery page |
| `cookbook/` | The financial services menu (`financial-services.md` and `.json`), one folder per recipe, and `index.json` |
| `docs/films/` | Short films, one MP4 per kind of work, and the page that plays them |
| `plugins/launchpad/` | Source of the Launchpad for Cowork plugin |
| `plugins/demo/` | Demonstration plugins with sample data, once reviewed for public release |
| `tools/` | Scripts that build and check the plugin packages |
| Releases | The plugin package (.zip) for each version |

## How Cowork uses this repository

- Everything Cowork follows ships inside the plugin package: skills, scripts, recipes and sample data. Each release is built from this repository and reviewed. Cowork does not download instructions while it runs.
- Pictures load from this site when a card shows them. Every card still reads well if a picture cannot load.
- Answers to "How do I…?" come from Microsoft Learn, Microsoft's public documentation, through a read-only connector that needs no sign-in.

## Install

### For one person, to try it

1. Download the latest .zip from Releases. Do not unzip it.
2. In Copilot Cowork, choose Customize, then Plugins, then Upload plugin, and choose who can use it.
3. Start a new conversation and type **Get me started**.

### For your organisation

1. Download the latest .zip from Releases.
2. In the Microsoft 365 admin center, open Manage apps and choose Upload custom app. Choose the ellipsis (...), then Add agent, and upload the .zip.
3. People then find Launchpad for Cowork in Cowork under Customize, Plugins, in the Discover section.

Custom plugins run in Cowork on the web and desktop, not on mobile.

## What Launchpad reads and keeps

- It reads nothing until you agree. It then looks at calendar titles, email subjects and file names from the last two weeks, and it reads a whole file only when you choose that file.
- It keeps nothing unless you say so. A short profile is saved only with your OK, and you can show, change or delete it.
- It never sends, posts, shares or schedules anything without your approval of that exact action.

## Pictures and networks

Launchpad's cards show pictures from `scott-adams.ai`, the address of this site, which the plugin declares. If your network blocks it, the pictures do not appear, but every step still works.

## Feedback

[Add how people should give feedback, for example GitHub issues.]
