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

from dolfinx import DirichletBC, Function
from multiphenics.cpp import cpp

def DecorateGetEigenPair(SLEPcEigenSolver):
    class DecoratedSLEPcEigenSolver(SLEPcEigenSolver):
        def get_eigenpair(self, r_fun, c_fun, i):
            assert isinstance(r_fun, Function)
            assert isinstance(c_fun, Function)
            return SLEPcEigenSolver.get_eigenpair(self, r_fun._cpp_object, c_fun._cpp_object, i)

    return DecoratedSLEPcEigenSolver

def SLEPcEigenSolver(A, B=None, bcs=None):
    if bcs is None:
        SLEPcEigenSolver = DecorateGetEigenPair(cpp.la.SLEPcEigenSolver)
        eigen_solver = SLEPcEigenSolver(A.getComm().tompi4py())
    else:
        assert isinstance(bcs, (DirichletBC, list))
        if isinstance(bcs, DirichletBC):
            bcs = [bcs]
        else:
            assert all([isinstance(bc, DirichletBC) for bc in bcs])
        SLEPcEigenSolver = DecorateGetEigenPair(cpp.la.CondensedSLEPcEigenSolver)
        eigen_solver = SLEPcEigenSolver(A.getComm().tompi4py())
        eigen_solver.set_boundary_conditions(bcs)

    eigen_solver.set_operators(A, B)
    return eigen_solver
