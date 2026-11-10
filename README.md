# Cowork Cookbook

Recipes, plugins and pictures that help people put Copilot Cowork to work on the work they already do. Launchpad, the customer plugin in this repository, uses them to suggest work, show what the result looks like and build a skill on the person's own files.

Status: preview. The repository sits on a personal account for now and may move to a Microsoft organisation. [Add the agreed support statement before sharing with customers.]

## What is in this repository

| Location | What it holds |
|---|---|
| `docs/` | The GitHub Pages site: the recipe menu and the pictures that Cowork cards show |
| `cookbook/` | One folder per recipe: the skill starting point, an example output, sample data and the sizing questions. `cookbook/index.json` lists every recipe |
| `plugins/launchpad/` | Source of the Launchpad plugin |
| `plugins/demo/` | Source of the demonstration plugins with sample data, once reviewed for public release |
| `tools/` | Scripts that build the plugin packages from the recipes and check them |
| Releases | The plugin packages (.zip) for each version |

## How Cowork uses this repository

- Everything Cowork follows ships inside the plugin package: skills, scripts, templates and recipe starting points. Each release is built from this repository and reviewed. Cowork does not download instructions while it runs.
- Pictures load from the GitHub Pages site when a card shows them. Larger examples open from the site in the browser.

## Install

### For one person, to try it

1. Download the latest .zip from Releases. Do not unzip it.
2. In Copilot Cowork, choose Customize, then Plugins, then Upload, and upload the .zip.
3. Start a new task and type **Get me started**.

### For your organisation

1. Download the latest .zip from Releases.
2. In the Microsoft 365 admin center, open Manage apps and choose Upload custom app. Choose the ellipsis (...), then Add agent, and upload the .zip.
3. People then find the plugin in Cowork under Sources & Skills, Plugins, in the Discover section.

Custom plugins run in Cowork on the web and desktop, not on mobile.

## What Launchpad reads and keeps

[Confirm these lines against the released version.]

- It reads nothing until you agree. It then looks at calendar titles, email subjects and file names from the last two weeks.
- It keeps nothing unless you say so. A short profile is saved only with your OK, and you can delete it.

## Pictures and networks

Cards in Cowork show pictures only from web addresses that the plugin declares. Launchpad declares `scadam.github.io`. If your network blocks GitHub, the pictures do not appear, but every step still works without them.

## Feedback

[Add how people should give feedback, for example GitHub issues.]
