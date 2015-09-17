// Copyright (C) 2011, 2012  Google Inc.
//
// This file is part of YouCompleteMe.
//
// YouCompleteMe is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// YouCompleteMe is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with YouCompleteMe.  If not, see <http://www.gnu.org/licenses/>.

#include "Result.h"
#include "standard.h"
#include "Utils.h"
#include <boost/algorithm/string.hpp>
#include <boost/function.hpp>
#include <algorithm>
#include <locale>

using boost::algorithm::istarts_with;

namespace YouCompleteMe {

#define kMax_Match_distance 0x7fffffff

Result::Result()
  :
  is_subsequence_( false ),
  char_match_distance_( kMax_Match_distance ),
  text_( NULL ) {
}


Result::Result( bool is_subsequence )
  :
  is_subsequence_( is_subsequence ),
  char_match_distance_( kMax_Match_distance ),
  text_( NULL ) {
}


Result::Result( bool is_subsequence,
                const std::string *text,
                int char_match_distance
  ):
  is_subsequence_( is_subsequence ),
  char_match_distance_( char_match_distance ),
  text_( text ) {
}

} // namespace YouCompleteMe
