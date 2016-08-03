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

#include "LetterNodeListMap.h"
#include "standard.h"
#include <algorithm>

namespace YouCompleteMe {

const int kNumLetters = NUM_LETTERS;
//static const int kLettersIndexStart = 0;
//static const int kNumbersIndexStart = 26;
const int kUpperToLowerCount = 'a'-'A';

    // map char to range 0-58
const char charIndex[256] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,37,38,39,40,41,42,43,39,44,45,46,47,48,49,50,51,27,28,29,30,31,32,33,34,35,36,52,53,54,55,56,57,58,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,44,42,45,41,49,39,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,44,43,45,49,37};

bool IsInAsciiRange( int index ) {
  return 0 <= index && index < 128;
}

int IndexForLetter( char letter ) {
    return charIndex[(unsigned char)letter];
}


LetterNodeListMap::LetterNodeListMap() {
}


LetterNodeListMap::LetterNodeListMap( const LetterNodeListMap &other ) {
  if ( other.letters_ )
    letters_.reset( new NearestLetterNodeArray( *other.letters_ ) );
}


NearestLetterNodeIndices &LetterNodeListMap::operator[] ( char letter ) {
  if ( !letters_ )
    letters_.reset( new NearestLetterNodeArray() );

  int letter_index = IndexForLetter( letter );

  return letters_->at( letter_index );
}


NearestLetterNodeIndices *LetterNodeListMap::ListPointerAt( char letter ) {
  if ( !letters_ )
    return NULL;

  return &letters_->at( IndexForLetter( letter ) );
}

} // namespace YouCompleteMe
