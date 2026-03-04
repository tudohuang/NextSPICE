def create_matrix(n):
    return [0.0] * (n * n)

def get_idx(r,c,n):
    return r * n + c

def stamping(matrix,r,c,n,value):
    idx = get_idx(r,c,n)
    matrix[idx] += value

def swap_rows(matrix, b, r1, r2, n):
    for j in range(n):
        idx1 = r1 * n + j
        idx2 = r2 * n + j
        matrix[idx1], matrix[idx2] = matrix[idx2], matrix[idx1]
    b[r1], b[r2] = b[r2], b[r1]

def gauss_solve(n, A, b):
    matrix = list(A)
    vector = list(b)

    for k in range(n):
        max_row = k
        max_val = abs(matrix[k * n + k])
        for i in range(k + 1, n):
            if abs(matrix[i * n + k]) > max_val:
                max_val = abs(matrix[i * n + k])
                max_row = i
        
        if max_val < 1e-18:
            raise ValueError("Matrix is singular! 電路可能存在懸空節點或無效連接。")

        if max_row != k:
            for j in range(k, n):
                idx1 = k * n + j
                idx2 = max_row * n + j
                matrix[idx1], matrix[idx2] = matrix[idx2], matrix[idx1]
            vector[k], vector[max_row] = vector[max_row], vector[k]

        pivot = matrix[k * n + k]
        for i in range(k + 1, n):
            factor = matrix[i * n + k] / pivot
            for j in range(k + 1, n):
                matrix[i * n + j] -= factor * matrix[k * n + j]
            vector[i] -= factor * vector[k]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        sum_ax = 0.0
        for j in range(i + 1, n):
            sum_ax += matrix[i * n + j] * x[j]
        x[i] = (vector[i] - sum_ax) / matrix[i * n + i]

    return x


def lu_solve(n, A, b):
    L = [0.0] * (n * n)
    U = [0.0] * (n * n)
    P = list(range(n))

    for i in range(n):
        L[i * n + i] = 1.0

    for k in range(n):
        max_row = k
        for i in range(k + 1, n):
            if abs(A[i * n + k]) > abs(A[max_row * n + k]):
                max_row = i
        
        if max_row != k:
            for j in range(k, n):
                idx1 = k * n + j
                idx2 = max_row * n + j
                A[idx1], A[idx2] = A[idx2], A[idx1]
            P[k], P[max_row] = P[max_row], P[k]
            for j in range(k):
                idx1 = k * n + j
                idx2 = max_row * n + j
                L[idx1], L[idx2] = L[idx2], L[idx1]

        pivot = A[k * n + k]
        if abs(pivot) < 1e-18:
            raise ValueError("Matrix is singular!")

        for i in range(k + 1, n):
            factor = A[i * n + k] / pivot
            L[i * n + k] = factor
            for j in range(k + 1, n):
                A[i * n + j] -= factor * A[k * n + j]
    
    for i in range(n):
        for j in range(i, n):
            U[i * n + j] = A[i * n + j]

    Pb = [0.0] * n
    for i in range(n):
        Pb[i] = b[P[i]]

    y = [0.0] * n
    for i in range(n):
        sum_ly = 0.0
        for j in range(i):
            sum_ly += L[i * n + j] * y[j]
        y[i] = (Pb[i] - sum_ly) / L[i * n + i]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        sum_ux = 0.0
        for j in range(i + 1, n):
            sum_ux += U[i * n + j] * x[j]
        x[i] = (y[i] - sum_ux) / U[i * n + i]

    return x    