// Copyright (C) 2011, 2012 Google Inc.
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include "Result.h"
#include "Utils.h"

namespace YouCompleteMe {

#define kMin_Score -0x7fffffff

Result::Result( bool is_subsequence )
  :
  is_subsequence_( is_subsequence ),
  score_( kMin_Score ),
  text_( NULL ) {
}


Result::Result( bool is_subsequence,
                const std::string *text,
                int score
  ):
  is_subsequence_( is_subsequence ),
  score_( score ),
  text_( text ) {
}

} // namespace YouCompleteMe
