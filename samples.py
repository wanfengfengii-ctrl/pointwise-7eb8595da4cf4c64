import sqlite3
from fractions import Fraction as F
from archive import create, Store
from analysis import Analysis

def payload(knots, mean, cov):
    return {"knots": list(map(str, knots)), "mean": list(map(str, mean)),
            "cov": [[str(x) for x in row] for row in cov]}

def open_sample(path=":memory:"):
    db = sqlite3.connect(path)
    create(db)
    store, jobs = Store(db), Analysis(db)
    store.replace("offset", payload([0,0,0,0,1,2,2,2,2],
                  [3]*5, [[1]*5 for _ in range(5)]))
    jobs.save("whole", "offset", 0, 2)
    jobs.save("empty", "offset", 1, 1)
    # Four repeated internal knots: discontinuous piecewise constants.
    store.replace("jump", payload([0]*4+[1]*4+[2]*4,
                  [1]*4+[7]*4, [[int(i == j) for j in range(8)] for i in range(8)]))
    jobs.save("jump-total", "jump", 0, 2)
    # All interior multiplicities 1..4; signed, singular PSD covariance vv^T.
    for multiplicity in range(1, 5):
        n = 4+multiplicity
        v = [F((-1)**i, i+1) for i in range(n)]
        mean = [F(i-2, i+1) for i in range(n)]
        store.replace("m"+str(multiplicity),
            payload([0]*4+[1]*multiplicity+[2]*4, mean,
                    [[a*b for b in v] for a in v]))
        jobs.save("m"+str(multiplicity), "m"+str(multiplicity), F(1,3), F(5,3))
    return db

if __name__ == "__main__":
    import sys
    db = open_sample(sys.argv[1])
    print("curves:", db.execute("SELECT count(*) FROM curves1").fetchone()[0])
    print("whole:", Analysis(db).run("whole"))
    db.close()
