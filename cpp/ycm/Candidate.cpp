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

#include "Candidate.h"
#include "Result.h"

namespace YouCompleteMe {

std::string _GetWordBoundaryChars( const std::string &text ) {
  std::string result;

  if (text.size() == 0) { return result; }
#define PushResultAtIndex(i)            \
    result.push_back(text[i]); \

  if (!ispunct( text[0] )) { PushResultAtIndex(0); }

  // first letter, first upper letter, letter after _ will be consider as a word boundary char
  for ( size_t i = 1; i < text.size(); ++i ) {
    bool is_good_uppercase = IsUppercase( text[ i ] ) &&
                             !IsUppercase( text[ i - 1 ] );
    bool is_alpha_after_punctuation = ispunct( text[ i - 1 ] ) &&
                                      isalpha( text[ i ] );

    if ( is_good_uppercase ||
         is_alpha_after_punctuation ) {
      PushResultAtIndex(i);
    }
  }

  return result;
}
  
std::string GetWordBoundaryChars( const std::string &text) {
    std::string s = _GetWordBoundaryChars(text);
    for ( char& c: s) { c = tolower(c); } // make test happy, compatibility
    return s;
};


Bitset LetterBitsetFromString( const std::string &text ) {
  Bitset letter_bitset;

  for ( char letter : text ) {
    letter_bitset.set( IndexForLetter( letter ) );
  }

  return letter_bitset;
}

int LongestCommonSubsequenceLength( const std::string &first,
                                    const std::string &second ) {
  const std::string &longer  = first.size() > second.size() ? first  : second;
  const std::string &shorter = first.size() > second.size() ? second : first;

  int longer_len  = longer.size();
  int shorter_len = shorter.size();

  std::vector<int> previous( shorter_len + 1, 0 );
  std::vector<int> current(  shorter_len + 1, 0 ); // [0, max_match_length_till_(index - 1), ...]

  for ( int i = 0; i < longer_len; ++i ) {
    int longer_char = tolower(longer[i]);
    for ( int j = 0; j < shorter_len; ++j ) {
      if ( longer_char == tolower( shorter[ j ] ) )
        current[ j + 1 ] = previous[ j ] + 1;
      else
        current[ j + 1 ] = std::max( current[ j ], previous[ j + 1 ] );
    }

    std::swap(previous, current);
  }

  return previous[ shorter_len ];
}

Candidate::Candidate( const std::string &text )
  :
  text_( text ),
  word_boundary_chars_( _GetWordBoundaryChars( text ) ),
  letters_present_( LetterBitsetFromString( text ) )
{
  // GetWordBoundaryChars(text, wbc_indexes_);
  // wbc_indexes_.push_back(text.size()); // push a index at len to calculate word length
  // wbc_indexes_.shrink_to_fit();
}

static std::tuple<bool, bool> match_char(char candidate, char query, bool case_sensitive) {
    if (candidate == query) { return std::make_tuple(true, false); }
    else{
      // when case_sensitive, upper only match upper, but lower can match upper too
      if (case_sensitive){
        if (IsLowercase(query) && candidate + kUpperToLowerCount == query){
            return std::make_tuple(true, true);
        }
      }
      else if ((IsLowercase(query) && candidate + kUpperToLowerCount == query)
               || (IsUppercase(query) && query + kUpperToLowerCount == candidate)){
            return std::make_tuple(true, true);
      }
    }
    return std::make_tuple(false, false);
}

#define kBasicScore 1000
/// shorter string get more continue score
#define ContinueScore (continue_count * continue_count * (1 + 2.0 * continue_count/candidate_len) * kBasicScore)
Result Candidate::QueryMatchResult( const std::string &query,
                                    bool case_sensitive ) const {
  const int length_punish = text_.size() * 3;
  double index_sum = -length_punish; // total score

  std::string::const_iterator query_iter = query.begin(), query_end = query.end();
  if ( query_iter == query_end )
    return Result( true, &text_, index_sum);

  std::string::size_type index = 0, candidate_len = text_.size();
  
  // score related
  // front give a little priority to back
  // short give a little priority to long
  // match case give a little priority to convert case
  
  // continue_count will increase when match,
  //  and get a lot of bonus when discontinue according to continue count.
  
  // word boundary give a lot of bonus according to similarity
  
  // the last char will get some extra bonus
  int continue_count = 0;
  int change_case_count = 0;

  // When the query letter is uppercase, then we force an uppercase match
  // but when the query letter is lowercase, then it can match both an
  // uppercase and a lowercase letter. This is by design and it's much
  // better than forcing lowercase letter matches.
  bool change_case;
  bool match;

  while ( index < candidate_len ) {
    std::tie( match, change_case ) = match_char(text_[index], *query_iter, case_sensitive);

    if ( match ){
      // score related
      index_sum -= index; // give *front* priority to *back*
      if ( change_case ) ++change_case_count; // give *match case* priority to *change case*
      ++continue_count; // match will increase continueFactor

      // move to next query char
      ++query_iter;

      // complete, return result
      if ( query_iter == query_end ) {
        if (continue_count > 1){ // additional bonus for last continue match
          index_sum += ContinueScore * 1.5;
          continue_count = 0;
        }
        int word_boundary_count = LongestCommonSubsequenceLength(query, word_boundary_chars_);
        if (word_boundary_count > 0) {
            double const word_boundary_char_utilization = word_boundary_count / (double)word_boundary_chars_.size();
            // double const query_match_wbc_ratio = word_boundary_count / (double)query.size();
            index_sum += word_boundary_count * word_boundary_count * (1 + word_boundary_char_utilization * 2) * kBasicScore;
        }
        // match last char, get extra bonus for shorter string
        if ( index + 1 == candidate_len ) index_sum += 1500 / (candidate_len * candidate_len) * kBasicScore;

        return Result( true, &text_,  index_sum - change_case_count);
      }
    }else {
      if (continue_count > 1){
        index_sum += ContinueScore;
      }
      continue_count = 0; // drop to 0 when not match
    }
    ++index;
  }
  return Result(false);
}

} // namespace YouCompleteMe
