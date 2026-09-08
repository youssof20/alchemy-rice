# Dependency resolution and trust

A rice remains config-only even when its appearance depends on packages that contain executable code. The manifest declares a capability, source, component type, and license. Alchemy—not the rice—maps that capability to a host package and generates any install command.

## Trust tiers

| Tier | Label | Meaning | Phase 6 behavior |
| --- | --- | --- | --- |
| A | Official distro package | A dated reviewed mapping points to an official enabled distro repository. | May be installed after exact plan review, token confirmation, and privilege approval. |
| B | Third-party package - review source | AUR, community repository, KDE Store, or creator release. | Source and command guidance are shown, but installation remains manual. |
| C | Manual install required | Arbitrary/manual source or a package claim without a reviewed mapping. | No automatic command is executed. |

AUR is always Tier B, even if a malformed database entry attempts to call it official. A manifest cannot promote its own trust tier.

## Resolve first

Export the dependency example, then inspect its local resolution:

```bash
alchemy rice-export examples/rice-v2-dependencies.json kvantum-workbench.rice
alchemy dependency-resolve kvantum-workbench.rice
```

Resolution performs no installation and no network search. For each dependency it shows:

- the declared source, license, and code/config/asset distinction;
- dated Plasma and component compatibility evidence;
- the reviewed distro package candidate and source page, if known;
- installed state and version where a provider query is available;
- the trust label and any unresolved or blocking evidence;
- the exact argument vector and privilege reason;
- a plan token bound to all security-relevant inputs.

`confirmed_broken` and `upstream_unsupported` records block a plan. An advanced user can request a new plan with `--allow-known-incompatible`; the override and warning become part of the token. `user_report_only` and `unknown` evidence remain visible and are not misrepresented as universal proof.

## Separate installation

Only a missing or mismatched Tier A package with confirmed distro mapping and available provider tools is automatable:

```bash
alchemy dependency-install kvantum-workbench.rice kvantum-style-engine \
  --plan-token TOKEN_FROM_DEPENDENCY_RESOLVE --yes
```

The install command is separate from desktop configuration. It takes the shared mutation lock, reloads the canonical rice, refreshes the environment and package observation, and recomputes the plan. Any changed hash, provider, package, compatibility result, environment, command, or installed state invalidates the token.

Privileged provider plans use `pkexec`; no generic `sudo` string or shell command is constructed. Package names come from the reviewed compatibility database rather than manifest command text. After the provider exits, Alchemy queries the local package database again. Only a verified result creates an owner-only receipt under the local Alchemy state directory.

Alchemy does not auto-uninstall receipt packages during rice revert. A dependency may be shared, may have been independently requested, or may now be needed by another application.

## Providers and immutable hosts

Phase 6 contains adapters for pacman, paru/yay, dnf, apt, and zypper. A provider can exist without a current bundled mapping; that remains unresolved rather than guessed. AUR plans are visible but not automated because their build recipes are third-party code and may require interaction.

Immutable and Nix-managed systems refuse host package mutation. A future user-local or declarative provider can handle those systems without weakening this boundary.

## Compatibility data

The public `compatibility/` directory contains:

- `plasma.json` for engine-level Plasma evidence;
- `components.json` for capability-specific Plasma evidence;
- `distro-packages.json` for dated package/provider/repository mappings.

Allowed evidence states are `confirmed_working`, `confirmed_broken`, `unknown`, `upstream_unsupported`, and `user_report_only`. Package mapping confirmation means the named package was verified in the linked repository on the recorded date; it does not prove runtime compatibility. Entries should be updated through normal reviewed repository changes with authoritative source links.
