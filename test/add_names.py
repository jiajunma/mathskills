#!/usr/bin/env python3
"""Add descriptive names to each mathematical object in the analysis JSON."""

import json

NAMES = {
    # === Theorems ===
    "theorem:1.5": "Grading of A under the x₀-grading",
    "theorem:1.6": "Polynomial algebra structure of A ≅ A(N)",
    "theorem:1.7": "Polynomial algebra structure of S(p̄)^N",
    "theorem:1.8": "Graded injection S(p̄)^N ↪ S(m)",
    "theorem:2.2": "Graded n-reduced action on Gr U(p̄)",
    "theorem:2.3": "Exact sequence for U(p̄)^N filtration",
    "theorem:2.4": "Freeness of U(p̄) as right U(p̄)^N-module",
    "theorem:3.1": "Annihilator decomposition of cyclic Whittaker vectors",
    "theorem:3.2": "Characterization of Whittaker vectors via U(p̄)^N",
    "theorem:3.3": "Classification of Whittaker modules by cyclic U(p̄)^N-modules",
    "theorem:3.4": "Irreducibility criterion for Whittaker modules",
    "theorem:4.1": "Whittaker module embedding into U(n)* ⊗ Wh(V)",
    "theorem:4.2": "Whittaker vectors in tensor products",
    "theorem:4.3": "Vanishing of n-cohomology for η-finite modules",
    "theorem:4.4": "Dimension formula for Whittaker vectors in composition series",
    "theorem:4.6": "Exact sequences for η-finite subquotients",
    "theorem:5.1": "Dimension of Whittaker vectors in completed Verma modules",
    "theorem:5.2": "Annihilator equality for Whittaker submodules",
    "theorem:6.2.1": "Cyclic generation of spherical principal series",
    "theorem:6.2.2": "Freeness of spherical principal series over U(n)",
    "theorem:6.4": "Dimension formula for Whittaker vectors in induced modules",
    "theorem:7.1": "Admissible nilpotents are Richardson elements",

    # === Propositions ===
    "proposition:1.4.1": "N-action on S(p̄) via Killing form",
    "proposition:1.4.2": "Explicit formula for the N-action",
    "proposition:1.4.3": "Degree-lowering by the N-action",
    "proposition:1.4.4": "S(p̄)^N is an x₀-graded subalgebra",
    "proposition:1.5.1": "A is an N-submodule of S(p̄)",
    "proposition:1.5.2": "Scaling property of r(t) on S(p̄)",
    "proposition:2.1.1": "Exact sequence for x₀-filtration of U(p̄)",
    "proposition:2.1.2": "Graded isomorphism τ: Gr U(p̄) → S(p̄)",
    "proposition:2.5": "Ã is an n-module via the *-action",
    "proposition:2.6": "Center of U(g) embeds into U(p̄)^N",
    "proposition:4.3.1": "V_η is a U-submodule",
    "proposition:4.3.2": "Existence of Whittaker vectors in finite U(n)-orbits",
    "proposition:4.3.3": "η-finiteness criterion via composition series",
    "proposition:4.5": "η-finiteness of V_η via Whittaker composition series",
    "proposition:4.6": "Artin-Rees type lemma for U(n)-modules",
    "proposition:5.1": "Generalized Verma modules as n-modules",
    "proposition:5.3": "Irreducibility criterion for generalized Verma modules",
    "proposition:7.3.1": "Admissible nilpotents for gl(n;K)",
    "proposition:7.3.2": "Admissible nilpotents for g(n,q;K)",
    "proposition:7.3.3": "Admissible nilpotents for symplectic and orthogonal algebras",

    # === Lemmas ===
    "lemma:1.5.1": "Equivariance of r(t) with N-action",
    "lemma:1.7": "Leading term of S(p̄)^N lies in p̄^f",
    "lemma:2.2.1": "n-reduced action on powers",
    "lemma:2.3": "U(p̄)^N is a subalgebra (Kostant)",
    "lemma:2.5.1": "Relation between · and * actions on Ã",
    "lemma:2.5.2": "Non-degeneracy of *-action on Ã",
    "lemma:2.5.3": "Commutation of *-action with U(p̄)^N multiplication",
    "lemma:3.1": "Structure of X = {v ∈ U(p̄) | (x·v)w=0}",
    "lemma:4.3": "Vanishing of n-cohomology for Whittaker modules",
    "lemma:4.5": "Whittaker vectors determine η-finite submodules",
    "lemma:4.6": "Exact sequence for η-finite parts",
    "lemma:6.2": "Direct sum decomposition for principal series",
    "lemma:6.3.1": "Tensor product filtration by P-representations",
    "lemma:6.3.2": "Character identity for tensor products",
    "lemma:7.2": "Ordering condition for admissible nilpotents in B,C,D types",

    # === Corollaries ===
    "corollary:1.7.1": "Coordinate system on [n,f] from generators of A",
    "corollary:1.7.2": "Coordinate system on Δ from generators of S(p̄)^N",
    "corollary:1.7.3": "Dimension equality dim p̄^f = dim m",
    "corollary:2.3.1": "Finite generation of U(p̄)^N",
    "corollary:2.3.2": "Injectivity of generalized Harish-Chandra homomorphism",
    "corollary:4.5": "Complete reducibility of V_η iff Wh(V) completely reducible",
    "corollary:6.2": "Dimension of Whittaker space in spherical principal series",
    "corollary:7.1": "Real admissible nilpotents via M(Σ)-orbits",

    # === Remarks ===
    "remark:1.4": "N-invariants and the derivation action",
    "remark:1.5": "Natural action of P on N via coset projection",
    "remark:2.5": "Equivalence of ·-action and *-action vanishing",
    "remark:3.2": "Whittaker space as cyclic U(p̄)^N-module",
    "remark:3.4": "Irreducible Whittaker submodules generate irreducible U-modules",
    "remark:4.3": "Whittaker modules are η-finite",

    # === Conjecture ===
    "conjecture:5.1": "Surjectivity conjecture for infinite-dimensional Verma completions",
}

with open('test/Lynch_final.json', 'r') as f:
    data = json.load(f)

named = 0
for obj in data['objects']:
    if obj['id'] in NAMES:
        obj['title'] = NAMES[obj['id']]
        named += 1

with open('test/Lynch_final.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Named {named}/{len([o for o in data['objects'] if o['type'] != 'proof'])} non-proof objects")
