# Copyright (C) 2016 by the block_ext authors
#
# This file is part of block_ext.
#
# block_ext is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# block_ext is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with block_ext. If not, see <http://www.gnu.org/licenses/>.
#

from dolfin import PETScSNESSolver
from block_ext.monolithic_matrix import MonolithicMatrix

class BlockPETScSNESSolver(PETScSNESSolver):
    def __init__(self, problem):
        PETScSNESSolver.__init__(self)
        self.problem = problem
    
    def solve(self):
        PETScSNESSolver.solve(self, self.problem, self.problem.monolithic_solution)
        # Convert monolithic_solution into block_solution
        self.problem.monolithic_solution.copy_values_to(self.problem.block_solution.block_vector())
        # Clean up monolithic residual and jacobian, since the next time that solve will be called
        # they will reference different petsc vector and matrix
        self.problem.monolithic_residual = None
        self.problem.monolithic_jacobian = None
