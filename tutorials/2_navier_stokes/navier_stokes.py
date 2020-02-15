# Copyright (C) 2016-2020 by the multiphenics authors
#
# This file is part of multiphenics.
#
# multiphenics is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# multiphenics is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with multiphenics. If not, see <http://www.gnu.org/licenses/>.
#

from numpy import isclose, where, zeros
from petsc4py import PETSc
from ufl import *
from dolfinx import *
from dolfinx.cpp.mesh import GhostMode
from dolfinx.fem import assemble_matrix, assemble_scalar, assemble_vector, locate_dofs_topological
from dolfinx.io import XDMFFile
from multiphenics import *
from multiphenics.fem import DirichletBCLegacy

"""
In this tutorial we compare the formulation and solution
of a Navier-Stokes by standard FEniCS code (using the
MixedElement class) and multiphenics code.
"""

# Constitutive parameters
nu = 0.01
def u_in_eval(x):
    values = zeros((2, x.shape[1]))
    values[0, :] = 1.0
    return values
def u_wall_eval(x):
    return zeros((2, x.shape[1]))

# Solver parameters
def set_solver_parameters(solver):
    solver.max_it = 20

# Mesh
mesh = XDMFFile(MPI.comm_world, "data/backward_facing_step.xdmf").read_mesh(GhostMode.none)
subdomains = XDMFFile(MPI.comm_world, "data/backward_facing_step_subdomains.xdmf").read_mf_size_t(mesh)
boundaries = XDMFFile(MPI.comm_world, "data/backward_facing_step_boundaries.xdmf").read_mf_size_t(mesh)
boundaries_1 = where(boundaries.values == 1)[0]
boundaries_2 = where(boundaries.values == 2)[0]

# Function spaces
V_element = VectorElement("Lagrange", mesh.ufl_cell(), 2)
Q_element = FiniteElement("Lagrange", mesh.ufl_cell(), 1)

# -------------------------------------------------- #

# STANDARD FEniCS FORMULATION BY FEniCS MixedElement #
def run_monolithic():
    # Function spaces
    W_element = MixedElement(V_element, Q_element)
    W = FunctionSpace(mesh, W_element)

    # Test and trial functions: monolithic
    vq = TestFunction(W)
    (v, q) = split(vq)
    dup = TrialFunction(W)
    up = Function(W)
    (u, p) = split(up)

    # Variational forms
    F = (
            nu*inner(grad(u), grad(v))*dx
          + inner(grad(u)*u, v)*dx
          - div(v)*p*dx
          + div(u)*q*dx
        )
    J = derivative(F, up, dup)

    # Boundary conditions
    u_in = Function(W.sub(0).collapse())
    u_in.interpolate(u_in_eval)
    u_wall = Function(W.sub(0).collapse())
    u_wall.interpolate(u_wall_eval)
    bdofs_V_1 = locate_dofs_topological((W.sub(0), W.sub(0).collapse()), mesh.topology.dim - 1, boundaries_1)
    bdofs_V_2 = locate_dofs_topological((W.sub(0), W.sub(0).collapse()), mesh.topology.dim - 1, boundaries_2)
    inlet_bc = DirichletBC(u_in, bdofs_V_1, W.sub(0))
    wall_bc = DirichletBC(u_wall, bdofs_V_2, W.sub(0))
    bc = [inlet_bc, wall_bc]

    # Class for interfacing with the Newton solver
    class NavierStokesProblem(NonlinearProblem):
        def __init__(self, F, up, bc, J):
            NonlinearProblem.__init__(self)
            self._F = F
            self._up = up
            self._bc = bc
            self._J = J
            self._F_vec = None
            self._J_mat = None

        def form(self, x):
            x.ghostUpdate(addv=PETSc.InsertMode.INSERT, mode=PETSc.ScatterMode.FORWARD)

        def F(self, _):
            if self._F_vec is None:
                self._F_vec = assemble_vector(self._F)
            else:
                with self._F_vec.localForm() as f_local:
                    f_local.set(0.0)
                assemble_vector(self._F_vec, self._F)
            self._F_vec.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
            DirichletBCLegacy.apply(self._bc, self._F_vec, self._up.vector)
            return self._F_vec

        def J(self, _):
            if self._J_mat is None:
                self._J_mat = assemble_matrix(self._J)
            else:
                self._J_mat.zeroEntries()
                assemble_matrix(self._J_mat, self._J)
            self._J_mat.assemble()
            DirichletBCLegacy.apply(self._bc, self._J_mat, 1.0)
            return self._J_mat

    # Solve
    problem = NavierStokesProblem(F, up, bc, J)
    solver = NewtonSolver(mesh.mpi_comm())
    set_solver_parameters(solver)
    solver.solve(problem, up.vector)

    # Extract solutions
    return up

up_m = run_monolithic()

# -------------------------------------------------- #

#                 multiphenics FORMULATION           #
def run_block():
    # Function spaces
    W_element = BlockElement(V_element, Q_element)
    W = BlockFunctionSpace(mesh, W_element)

    # Test and trial functions
    vq = BlockTestFunction(W)
    (v, q) = block_split(vq)
    dup = BlockTrialFunction(W)
    up = BlockFunction(W)
    (u, p) = block_split(up)

    # Variational forms
    F = [nu*inner(grad(u), grad(v))*dx + inner(grad(u)*u, v)*dx - div(v)*p*dx,
         div(u)*q*dx]
    J = block_derivative(F, up, dup)

    # Boundary conditions
    u_in = Function(W.sub(0))
    u_in.interpolate(u_in_eval)
    u_wall = Function(W.sub(0))
    u_wall.interpolate(u_wall_eval)
    bdofs_V_1 = locate_dofs_topological(W.sub(0), mesh.topology.dim - 1, boundaries_1)
    bdofs_V_2 = locate_dofs_topological(W.sub(0), mesh.topology.dim - 1, boundaries_2)
    inlet_bc = DirichletBC(u_in, bdofs_V_1)
    wall_bc = DirichletBC(u_wall, bdofs_V_2)
    bc = BlockDirichletBC([[inlet_bc, wall_bc], []])

    # Solve
    problem = BlockNonlinearProblem(F, up, bc, J)
    solver = BlockNewtonSolver(mesh.mpi_comm())
    set_solver_parameters(solver)
    solver.solve(problem, up.block_vector)

    # Extract solutions
    return up

up_b = run_block()

# -------------------------------------------------- #

#                  ERROR COMPUTATION                 #
def run_error(up_m, up_b):
    (u_m, p_m) = up_m.split()
    (u_b, p_b) = up_b.block_split()
    u_m_norm = sqrt(MPI.sum(mesh.mpi_comm(), assemble_scalar(inner(grad(u_m), grad(u_m))*dx)))
    err_u_norm = sqrt(MPI.sum(mesh.mpi_comm(), assemble_scalar(inner(grad(u_b - u_m), grad(u_b - u_m))*dx)))
    p_m_norm = sqrt(MPI.sum(mesh.mpi_comm(), assemble_scalar(inner(p_m, p_m)*dx)))
    err_p_norm = sqrt(MPI.sum(mesh.mpi_comm(), assemble_scalar(inner(p_b - p_m, p_b - p_m)*dx)))
    print("Relative error for velocity component is equal to", err_u_norm/u_m_norm)
    print("Relative error for pressure component is equal to", err_p_norm/p_m_norm)
    assert isclose(err_u_norm/u_m_norm, 0., atol=1.e-10)
    assert isclose(err_p_norm/p_m_norm, 0., atol=1.e-10)

run_error(up_m, up_b)
