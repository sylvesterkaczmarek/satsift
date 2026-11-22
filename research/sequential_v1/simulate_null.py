#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .formal import ChangePointMixtureEProcess


def run_path(bits, *, q0: float, threshold: float) -> dict:
    process=ChangePointMixtureEProcess(q0=q0)
    maximum=1.0
    crossing=None
    for index,bit in enumerate(bits,1):
        update=process.update(bit)
        if update.wealth>maximum:
            maximum=update.wealth
        if crossing is None and update.wealth>=threshold:
            crossing=index
    return {'maximum_wealth':maximum,'crossing_index':crossing}


def iid_path(rng, length, p):
    return [int(rng.random()<p) for _ in range(length)]


def predictable_valid_path(rng, length, q0):
    # The success probability is deterministic/predictable and never exceeds q0.
    result=[]
    for t in range(length):
        p=q0 if (t//25)%2==0 else q0/4.0
        result.append(int(rng.random()<p))
    return result


def clustered_same_marginal_path(rng, length, marginal, persistence=.50):
    # Stationary marginal is approximately `marginal`, but P(X_t=1 | X_{t-1}=1)=persistence.
    # When persistence > marginal the conditional bound q0=marginal is violated by construction.
    p01=marginal*(1.0-persistence)/(1.0-marginal)
    state=int(rng.random()<marginal)
    result=[]
    for _ in range(length):
        result.append(state)
        p=persistence if state else p01
        state=int(rng.random()<p)
    return result


def experiment(name, generator, *, replicates, q0, threshold):
    crossings=0
    crossing_times=[]
    maxima=[]
    for replica in range(replicates):
        rng=random.Random(20260815+1000003*replica+sum(map(ord,name)))
        path=generator(rng)
        result=run_path(path,q0=q0,threshold=threshold)
        maxima.append(result['maximum_wealth'])
        if result['crossing_index'] is not None:
            crossings+=1; crossing_times.append(result['crossing_index'])
    maxima.sort()
    return {
        'name':name,
        'replicates':replicates,
        'crossings':crossings,
        'crossing_probability':crossings/replicates,
        'median_crossing_index':None if not crossing_times else sorted(crossing_times)[len(crossing_times)//2],
        'median_maximum_wealth':maxima[len(maxima)//2],
        'p95_maximum_wealth':maxima[min(len(maxima)-1,int(.95*len(maxima)))],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--replicates',type=int,default=5000)
    parser.add_argument('--length',type=int,default=500)
    parser.add_argument('--q0',type=float,default=.05)
    parser.add_argument('--alpha',type=float,default=.05)
    parser.add_argument('--output',type=Path,default=Path('benchmark-results/sequential-v1-null-simulations.json'))
    args=parser.parse_args()
    if args.replicates<100 or args.length<10:
        raise SystemExit('simulation size is too small')
    threshold=1.0/args.alpha
    q0=args.q0
    length=args.length
    simulations=[
        experiment('iid-boundary',lambda rng:iid_path(rng,length,q0),replicates=args.replicates,q0=q0,threshold=threshold),
        experiment('predictable-valid-nonstationary',lambda rng:predictable_valid_path(rng,length,q0),replicates=args.replicates,q0=q0,threshold=threshold),
        experiment('clustered-same-marginal-conditional-bound-violated',lambda rng:clustered_same_marginal_path(rng,length,q0,.50),replicates=args.replicates,q0=q0,threshold=threshold),
        experiment('misspecified-rate-1.5x-q0',lambda rng:iid_path(rng,length,min(.99,1.5*q0)),replicates=args.replicates,q0=q0,threshold=threshold),
    ]
    document={
        'schema':'smd-sequential-v1-null-simulations',
        'seed_rule':'20260815 + 1000003*replica + character-sum(name)',
        'q0':q0,'alpha':args.alpha,'wealth_threshold':threshold,
        'updates_per_path':length,'replicates':args.replicates,
        'formal_interpretation':'Only scenarios whose conditional success probability never exceeds q0 satisfy the theorem assumption. Under that assumption Ville gives crossing probability <= alpha for an unbounded horizon; finite Monte Carlo estimates need not equal alpha.',
        'failure_interpretation':'Clustered and misspecified scenarios deliberately violate the conditional bound and demonstrate why marginal calibration alone cannot justify a formal claim.',
        'simulations':simulations,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(document,indent=2)+'\n')
    print(json.dumps(document,indent=2))


if __name__=='__main__': main()
