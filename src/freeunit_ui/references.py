"""What the configuration points at, and whether it is there.

A schema can say that ``pass`` is a string. It cannot say that
``"pass": "applications/blog"`` must name an application that exists — that
lives in the document, not the schema, and it is the mistake people actually
make: a listener left pointing at a renamed application, a route naming a
deleted one, a listener using a certificate bundle nobody uploaded.

Nothing here is authoritative either. Unit resolves ``pass`` destinations that
contain variables at request time, so those are reported as undecidable rather
than broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["application", "route", "certificate"]


@dataclass(frozen=True, slots=True)
class Reference:
    """One pointer from somewhere in the configuration to something else."""

    source: str
    kind: Kind
    target: str
    #: ``None`` when the destination is built from variables and only Unit can
    #: resolve it, at request time.
    resolved: bool | None

    @property
    def is_broken(self) -> bool:
        """Whether this definitely points at something that is not configured."""
        return self.resolved is False


@dataclass(frozen=True, slots=True)
class Report:
    """Every reference in a configuration, and what nothing points at."""

    references: tuple[Reference, ...] = ()
    unused_applications: tuple[str, ...] = ()
    unused_certificates: tuple[str, ...] = ()

    @property
    def broken(self) -> tuple[Reference, ...]:
        """References that name something absent."""
        return tuple(r for r in self.references if r.is_broken)


def _names(value: Any) -> list[str]:
    """A certificate member is a bundle name or a list of them."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _destination(target: str, applications: set[str], routes: Any) -> tuple[Kind, bool | None]:
    """Classify a pass destination and say whether it resolves."""
    # Unit expands variables such as $host when the request arrives, so a
    # destination containing one cannot be judged here.
    dynamic = "$" in target

    head, _, rest = target.partition("/")
    if head == "applications":
        return "application", None if dynamic else rest in applications
    if head == "routes":
        if not rest:
            return "route", isinstance(routes, list)
        return "route", None if dynamic else isinstance(routes, dict) and rest in routes
    # Anything else (upstreams in newer releases, say) is not judged.
    return "route", None


def _steps(routes: Any) -> list[tuple[str, Any]]:
    """Yield ``(pointer, step)`` for every route step, named or not."""
    found: list[tuple[str, Any]] = []
    if isinstance(routes, list):
        found += [(f"/routes/{i}", step) for i, step in enumerate(routes)]
    elif isinstance(routes, dict):
        for name, steps in routes.items():
            if isinstance(steps, list):
                found += [(f"/routes/{name}/{i}", step) for i, step in enumerate(steps)]
    return found


def _actions(action: Any, pointer: str) -> list[tuple[str, Any]]:
    """Yield an action and any fallback nested inside it."""
    if not isinstance(action, dict):
        return []
    found = [(pointer, action)]
    fallback = action.get("fallback")
    if isinstance(fallback, dict):
        found += _actions(fallback, f"{pointer}/fallback")
    return found


def analyse(config: Any, certificates: set[str] | None = None) -> Report:
    """Find every reference in ``config`` and what nothing points at.

    Args:
        config: The whole configuration document.
        certificates: Names of the stored certificate bundles.

    Returns:
        A report of references, broken ones included, and of applications and
        certificate bundles nothing refers to.
    """
    if not isinstance(config, dict):
        return Report()

    stored = certificates or set()
    applications_value = config.get("applications")
    applications = set(applications_value) if isinstance(applications_value, dict) else set()
    routes = config.get("routes")
    references: list[Reference] = []

    listeners = config.get("listeners")
    for address, listener in listeners.items() if isinstance(listeners, dict) else ():
        if not isinstance(listener, dict):
            continue
        if isinstance(listener.get("pass"), str):
            kind, resolved = _destination(listener["pass"], applications, routes)
            references.append(
                Reference(f"/listeners/{address}/pass", kind, listener["pass"], resolved)
            )
        tls = listener.get("tls")
        if isinstance(tls, dict):
            references += [
                Reference(
                    f"/listeners/{address}/tls/certificate", "certificate", name, name in stored
                )
                for name in _names(tls.get("certificate"))
            ]

    for pointer, step in _steps(routes):
        if not isinstance(step, dict):
            continue
        for action_pointer, action in _actions(step.get("action"), f"{pointer}/action"):
            if isinstance(action.get("pass"), str):
                kind, resolved = _destination(action["pass"], applications, routes)
                references.append(
                    Reference(f"{action_pointer}/pass", kind, action["pass"], resolved)
                )

    referenced_apps = {r.target.partition("/")[2] for r in references if r.kind == "application"}
    referenced_certs = {r.target for r in references if r.kind == "certificate"}

    return Report(
        references=tuple(references),
        unused_applications=tuple(sorted(applications - referenced_apps)),
        unused_certificates=tuple(sorted(stored - referenced_certs)),
    )
